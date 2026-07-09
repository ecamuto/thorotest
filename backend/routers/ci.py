"""Trigger a GitHub Actions workflow from a github integration and collect its
JUnit results when it finishes (background poll). See backend/github_actions.py.
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db, SessionLocal
from .. import models
from ..auth_utils import require_role
from ..github_actions import (
    GitHubActionsClient, ci_config, pick_dispatched_run, collect_run_results,
)
from ..gitlab_actions import (
    GitLabActionsClient, ci_config as gitlab_ci_config, collect_pipeline_results,
    _TERMINAL as GITLAB_TERMINAL,
)
from ..vcs import detect_provider

logger = logging.getLogger("thorotest.ci")
router = APIRouter(tags=["ci"])

WRITE_ROLES = require_role("admin", "manager")

POLL_INTERVAL = 15      # seconds between GitHub polls
FIND_TIMEOUT = 120      # seconds to locate the dispatched run
RUN_TIMEOUT = 1800      # seconds to wait for the run to complete

# In-memory registry of dispatch jobs (per-process; lost on restart).
_JOBS: dict[str, dict] = {}


def _fmt_duration(seconds) -> str | None:
    """Seconds → "4m 12s" / "38s" for the pipelines table, or None."""
    if not seconds:
        return None
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _gh_run_seconds(detail: dict) -> float | None:
    """Elapsed seconds of a GitHub run from its timestamps, or None."""
    start = detail.get("run_started_at") or detail.get("created_at")
    end = detail.get("updated_at")
    if not (start and end):
        return None
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    secs = (e - s).total_seconds()
    return secs if secs > 0 else None


def _upsert_pipeline(db, pid: str, **fields) -> None:
    """Create/update the Pipeline row the pipelines page shows, so a live
    "Run CI" dispatch appears there (running → pass/fail) — not just as a Run."""
    p = db.query(models.Pipeline).filter(models.Pipeline.id == pid).first()
    if p is None:
        p = models.Pipeline(id=pid)
        db.add(p)
    for k, v in fields.items():
        if v is not None:
            setattr(p, k, v)
    db.commit()


class CIRunRequest(BaseModel):
    workflow: Optional[str] = None    # override integration config
    ref: Optional[str] = None
    artifact: Optional[str] = None
    run_name: Optional[str] = None


def _resolve_cfg(intg, payload: CIRunRequest) -> dict:
    cfg = ci_config(intg)   # raises ValueError if repo_url isn't a github repo
    if payload.workflow:
        cfg["workflow"] = payload.workflow
    if payload.ref:
        cfg["ref"] = payload.ref
    if payload.artifact:
        cfg["artifact"] = payload.artifact
    return cfg


def _do_dispatch(cfg: dict) -> None:
    with GitHubActionsClient(cfg["token"]) as client:
        client.dispatch(cfg["owner"], cfg["repo"], cfg["workflow"], cfg["ref"])


def _orchestrate(job_id: str, cfg: dict, since: datetime, run_name: Optional[str]) -> None:
    """Blocking: find the dispatched run, wait for completion, import results.
    Runs in a worker thread (httpx client is sync)."""
    job = _JOBS[job_id]
    try:
        with GitHubActionsClient(cfg["token"]) as client:
            # 1. find the run our dispatch created
            job["status"] = "finding_run"
            deadline = time.time() + FIND_TIMEOUT
            run = None
            while time.time() < deadline:
                runs = client.list_runs(cfg["owner"], cfg["repo"], cfg["workflow"], branch=cfg["ref"])
                run = pick_dispatched_run(runs, since)
                if run:
                    break
                time.sleep(POLL_INTERVAL)
            if not run:
                raise RuntimeError("dispatched run not found (check workflow name / ref)")

            job["gh_run_id"] = run["id"]
            job["gh_run_url"] = run.get("html_url")
            job["status"] = "running"

            # Record the live run on the pipelines page (running → pass/fail).
            pipeline_row_id = f"gh-run-{run['id']}"
            job["pipeline_row_id"] = pipeline_row_id
            db0 = SessionLocal()
            try:
                _upsert_pipeline(
                    db0, pipeline_row_id,
                    name=run_name or run.get("name") or cfg["workflow"],
                    platform="github", status="running",
                    commit=(run.get("head_sha") or "")[:7] or None,
                    branch=run.get("head_branch") or cfg["ref"],
                    author=(run.get("actor") or {}).get("login"),
                    when="just now",
                )
            finally:
                db0.close()

            # 2. poll until completed
            deadline = time.time() + RUN_TIMEOUT
            while time.time() < deadline:
                detail = client.get_run(cfg["owner"], cfg["repo"], run["id"])
                if detail.get("status") == "completed":
                    job["conclusion"] = detail.get("conclusion")
                    break
                time.sleep(POLL_INTERVAL)
            else:
                raise RuntimeError("run did not complete within timeout")

            # 3. collect JUnit artifact → import (own DB session for the thread)
            job["status"] = "collecting"
            db = SessionLocal()
            try:
                stats = collect_run_results(
                    db, client, cfg["owner"], cfg["repo"], run["id"],
                    cfg["artifact"], run_name,
                )
                concl = job.get("conclusion")
                _upsert_pipeline(
                    db, pipeline_row_id,
                    status="pass" if concl == "success" else "fail",
                    duration=_fmt_duration(_gh_run_seconds(detail)),
                )
            finally:
                db.close()

            job["status"] = "done"
            job["imported"] = stats
    except Exception as e:
        logger.warning("CI job %s failed: %s", job_id, e)
        job["status"] = "error"
        job["error"] = str(e)


def _do_dispatch_gitlab(cfg: dict) -> dict:
    with GitLabActionsClient(cfg["api_base"], cfg["token"]) as client:
        return client.trigger_pipeline(cfg["project"], cfg["ref"])


def _orchestrate_gitlab(job_id: str, cfg: dict, run_name: Optional[str]) -> None:
    """Blocking: poll the pipeline until it finishes, then import its test
    report. Runs in a worker thread."""
    job = _JOBS[job_id]
    pipeline_id = job["gl_pipeline_id"]
    try:
        with GitLabActionsClient(cfg["api_base"], cfg["token"]) as client:
            job["status"] = "running"
            deadline = time.time() + RUN_TIMEOUT
            while time.time() < deadline:
                detail = client.get_pipeline(cfg["project"], pipeline_id)
                if detail.get("status") in GITLAB_TERMINAL:
                    job["conclusion"] = detail.get("status")
                    break
                time.sleep(POLL_INTERVAL)
            else:
                raise RuntimeError("pipeline did not complete within timeout")

            job["status"] = "collecting"
            db = SessionLocal()
            try:
                stats = collect_pipeline_results(db, client, cfg["project"], pipeline_id, run_name)
                pid = job.get("pipeline_row_id")
                if pid:
                    concl = job.get("conclusion")
                    _upsert_pipeline(
                        db, pid,
                        status="pass" if concl == "success" else "fail",
                        duration=_fmt_duration(detail.get("duration")),
                    )
            finally:
                db.close()

            job["status"] = "done"
            job["imported"] = stats
    except Exception as e:
        logger.warning("CI job %s failed: %s", job_id, e)
        job["status"] = "error"
        job["error"] = str(e)


@router.post("/integrations/{intg_id}/ci/run")
async def ci_run(intg_id: str, payload: CIRunRequest, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Dispatch a workflow/pipeline and start collecting its results in the background."""
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        provider = detect_provider(intg.config or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Not a VCS integration: {e}")

    if provider == "gitlab":
        try:
            cfg = gitlab_ci_config(intg)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Not a GitLab integration: {e}")
        since = datetime.now(timezone.utc)
        try:
            pipeline = await asyncio.to_thread(_do_dispatch_gitlab, cfg)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Dispatch failed: {e}")

        job_id = uuid.uuid4().hex[:12]
        pipeline_row_id = f"gl-pipeline-{pipeline.get('id')}"
        _upsert_pipeline(
            db, pipeline_row_id,
            name=payload.run_name or f"GitLab pipeline #{pipeline.get('id')}",
            platform="gitlab", status="running",
            commit=(pipeline.get("sha") or "")[:7] or None,
            branch=pipeline.get("ref") or cfg["ref"], when="just now",
        )
        _JOBS[job_id] = {
            "id": job_id,
            "integration_id": intg_id,
            "workflow": "pipeline",
            "ref": cfg["ref"],
            "status": "running",
            "started_at": since.isoformat(),
            "gl_pipeline_id": pipeline.get("id"),
            "gh_run_url": pipeline.get("web_url"),
            "pipeline_row_id": pipeline_row_id,
        }
        asyncio.create_task(asyncio.to_thread(_orchestrate_gitlab, job_id, cfg, payload.run_name))
        return {"job_id": job_id, "status": "dispatched", "workflow": "pipeline", "ref": cfg["ref"]}

    try:
        cfg = _resolve_cfg(intg, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Not a GitHub integration: {e}")

    since = datetime.now(timezone.utc)
    try:
        await asyncio.to_thread(_do_dispatch, cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dispatch failed: {e}")

    job_id = uuid.uuid4().hex[:12]
    _JOBS[job_id] = {
        "id": job_id,
        "integration_id": intg_id,
        "workflow": cfg["workflow"],
        "ref": cfg["ref"],
        "status": "dispatched",
        "started_at": since.isoformat(),
    }
    asyncio.create_task(asyncio.to_thread(_orchestrate, job_id, cfg, since, payload.run_name))

    return {"job_id": job_id, "status": "dispatched", "workflow": cfg["workflow"], "ref": cfg["ref"]}


@router.get("/integrations/{intg_id}/ci/jobs/{job_id}")
def ci_job_status(intg_id: str, job_id: str, _: models.User = WRITE_ROLES):
    job = _JOBS.get(job_id)
    if not job or job.get("integration_id") != intg_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
