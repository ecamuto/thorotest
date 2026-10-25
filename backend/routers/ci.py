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
from ..schemas import PipelineOut

logger = logging.getLogger("thorotest.ci")
router = APIRouter(tags=["ci"])

WRITE_ROLES = require_role("admin", "manager")

POLL_INTERVAL = 15      # seconds between GitHub polls
FIND_TIMEOUT = 120      # seconds to locate the dispatched run
RUN_TIMEOUT = 1800      # seconds to wait for the run to complete

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


class LostJobLease(RuntimeError):
    """Raised when an obsolete worker tries to mutate a recovered job."""


def _update_job(job_id: str, *, worker_id: str | None = None, **fields) -> None:
    db = SessionLocal()
    try:
        query = db.query(models.CIJob).filter(models.CIJob.id == job_id)
        if worker_id is not None:
            query = query.filter(
                models.CIJob.queue_status == "processing",
                models.CIJob.worker_id == worker_id,
            )
        job = query.first()
        if not job:
            if worker_id is not None:
                raise LostJobLease(f"CI job {job_id} lease is no longer owned")
            raise RuntimeError(f"CI job {job_id} no longer exists")
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc).isoformat()
        db.commit()
    finally:
        db.close()


def _orchestrate(
    job_id: str,
    cfg: dict,
    since: datetime,
    run_name: Optional[str],
    worker_id: str | None = None,
) -> None:
    """Blocking: find the dispatched run, wait for completion, import results.
    Runs in a worker thread (httpx client is sync)."""
    with GitHubActionsClient(cfg["token"]) as client:
        # 1. find the run our dispatch created
        _update_job(job_id, worker_id=worker_id, status="finding_run")
        deadline = time.time() + FIND_TIMEOUT
        run = None
        while time.time() < deadline:
            runs = client.list_runs(
                cfg["owner"], cfg["repo"], cfg["workflow"], branch=cfg["ref"]
            )
            run = pick_dispatched_run(runs, since)
            if run:
                break
            time.sleep(POLL_INTERVAL)
        if not run:
            raise RuntimeError("dispatched run not found (check workflow name / ref)")

        _update_job(
            job_id,
            worker_id=worker_id,
            external_run_id=str(run["id"]),
            external_url=run.get("html_url"),
            status="running",
        )

        # Record the live run on the pipelines page (running → pass/fail).
        pipeline_row_id = f"gh-run-{run['id']}"
        _update_job(job_id, worker_id=worker_id, pipeline_row_id=pipeline_row_id)
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
                url=run.get("html_url"),
                integration_id=cfg.get("integration_id"),
            )
        finally:
            db0.close()

        # 2. poll until completed
        deadline = time.time() + RUN_TIMEOUT
        while time.time() < deadline:
            detail = client.get_run(cfg["owner"], cfg["repo"], run["id"])
            if detail.get("status") == "completed":
                conclusion = detail.get("conclusion")
                break
            time.sleep(POLL_INTERVAL)
        else:
            raise RuntimeError("run did not complete within timeout")

        # 3. collect JUnit artifact → import (own DB session for the thread)
        _update_job(job_id, worker_id=worker_id, status="collecting")
        db = SessionLocal()
        try:
            stats = collect_run_results(
                db, client, cfg["owner"], cfg["repo"], run["id"],
                cfg["artifact"], run_name,
            )
            _upsert_pipeline(
                db, pipeline_row_id,
                status="pass" if conclusion == "success" else "fail",
                duration=_fmt_duration(_gh_run_seconds(detail)),
                run_id=(stats.get("run_ids") or [None])[-1],
            )
        finally:
            db.close()

        _update_job(job_id, worker_id=worker_id, status="done", result=stats)


def _do_dispatch_gitlab(cfg: dict) -> dict:
    with GitLabActionsClient(cfg["api_base"], cfg["token"]) as client:
        return client.trigger_pipeline(cfg["project"], cfg["ref"])


def _orchestrate_gitlab(
    job_id: str,
    cfg: dict,
    run_name: Optional[str],
    worker_id: str | None = None,
) -> None:
    """Blocking: poll the pipeline until it finishes, then import its test
    report. Runs in a worker thread."""
    db_job = SessionLocal()
    try:
        query = db_job.query(models.CIJob).filter(models.CIJob.id == job_id)
        if worker_id is not None:
            query = query.filter(
                models.CIJob.queue_status == "processing",
                models.CIJob.worker_id == worker_id,
            )
        job = query.first()
        if not job or not job.external_run_id:
            raise RuntimeError("GitLab pipeline id missing from durable job")
        pipeline_id = int(job.external_run_id)
        pipeline_row_id = job.pipeline_row_id
    finally:
        db_job.close()

    with GitLabActionsClient(cfg["api_base"], cfg["token"]) as client:
        _update_job(job_id, worker_id=worker_id, status="running")
        deadline = time.time() + RUN_TIMEOUT
        while time.time() < deadline:
            detail = client.get_pipeline(cfg["project"], pipeline_id)
            if detail.get("status") in GITLAB_TERMINAL:
                conclusion = detail.get("status")
                break
            time.sleep(POLL_INTERVAL)
        else:
            raise RuntimeError("pipeline did not complete within timeout")

        _update_job(job_id, worker_id=worker_id, status="collecting")
        db = SessionLocal()
        try:
            stats = collect_pipeline_results(
                db, client, cfg["project"], pipeline_id, run_name
            )
            if pipeline_row_id:
                _upsert_pipeline(
                    db, pipeline_row_id,
                    status="pass" if conclusion == "success" else "fail",
                    duration=_fmt_duration(detail.get("duration")),
                    run_id=(stats.get("run_ids") or [None])[-1],
                )
        finally:
            db.close()

        _update_job(job_id, worker_id=worker_id, status="done", result=stats)


def execute_job(job_id: str, worker_id: str | None = None) -> None:
    """Load credentials at execution time and process one durable job."""
    db = SessionLocal()
    try:
        query = db.query(models.CIJob).filter(models.CIJob.id == job_id)
        if worker_id is not None:
            query = query.filter(
                models.CIJob.queue_status == "processing",
                models.CIJob.worker_id == worker_id,
            )
        job = query.first()
        if not job:
            raise RuntimeError("CI job not found")
        intg = (
            db.query(models.Integration)
            .filter(models.Integration.id == job.integration_id)
            .first()
        )
        if not intg:
            raise RuntimeError("CI integration was deleted")
        provider = job.provider
        run_name = job.run_name
        since = datetime.fromisoformat(job.started_at)
        if provider == "gitlab":
            cfg = gitlab_ci_config(intg)
        else:
            payload = CIRunRequest(
                workflow=job.workflow,
                ref=job.ref,
                artifact=job.artifact,
            )
            cfg = _resolve_cfg(intg, payload)
            cfg["integration_id"] = job.integration_id
    finally:
        db.close()

    if provider == "gitlab":
        _orchestrate_gitlab(job_id, cfg, run_name, worker_id)
    else:
        _orchestrate(job_id, cfg, since, run_name, worker_id)


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
            url=pipeline.get("web_url"),
            integration_id=intg_id,
        )
        now = since.isoformat()
        db.add(models.CIJob(
            id=job_id,
            integration_id=intg_id,
            provider="gitlab",
            workflow="pipeline",
            ref=cfg["ref"],
            artifact=None,
            run_name=payload.run_name,
            status="queued",
            queue_status="queued",
            started_at=now,
            updated_at=now,
            external_run_id=str(pipeline.get("id")),
            external_url=pipeline.get("web_url"),
            pipeline_row_id=pipeline_row_id,
        ))
        db.commit()
        return {"job_id": job_id, "status": "dispatched", "workflow": "pipeline", "ref": cfg["ref"]}

    try:
        cfg = _resolve_cfg(intg, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Not a GitHub integration: {e}")
    cfg["integration_id"] = intg_id

    since = datetime.now(timezone.utc)
    try:
        await asyncio.to_thread(_do_dispatch, cfg)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dispatch failed: {e}")

    job_id = uuid.uuid4().hex[:12]
    now = since.isoformat()
    db.add(models.CIJob(
        id=job_id,
        integration_id=intg_id,
        provider="github",
        workflow=cfg["workflow"],
        ref=cfg["ref"],
        artifact=cfg["artifact"],
        run_name=payload.run_name,
        status="queued",
        queue_status="queued",
        started_at=now,
        updated_at=now,
    ))
    db.commit()

    return {"job_id": job_id, "status": "dispatched", "workflow": cfg["workflow"], "ref": cfg["ref"]}


@router.get("/integrations/{intg_id}/ci/jobs/{job_id}")
def ci_job_status(intg_id: str, job_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    job = db.query(models.CIJob).filter(
        models.CIJob.id == job_id,
        models.CIJob.integration_id == intg_id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "integration_id": job.integration_id,
        "workflow": job.workflow,
        "ref": job.ref,
        "status": job.status,
        "queue_status": job.queue_status,
        "provider": job.provider,
        "attempts": job.attempts,
        "started_at": job.started_at,
        "gh_run_id": job.external_run_id,
        "gh_run_url": job.external_url,
        "pipeline_row_id": job.pipeline_row_id,
        "imported": job.result,
        "error": job.error,
    }


# ── Reconcile stuck 'running' rows against the provider ─────────
# The durable worker normally recovers an expired job lease after a process
# restart. This endpoint remains a manual repair path for historical pipeline
# rows or provider runs created before durable jobs were introduced: it
# re-queries the provider for the real status of any 'running' pipeline (keyed by
# the run id encoded in the row id + the stored integration), imports results
# when it finds one finished, and flips the row to pass/fail. Idempotent.

def _reconcile_github(db, pipe, intg) -> bool:
    run_id = pipe.id[len("gh-run-"):]
    if not run_id.isdigit():
        return False
    cfg = ci_config(intg)
    with GitHubActionsClient(cfg["token"]) as client:
        detail = client.get_run(cfg["owner"], cfg["repo"], int(run_id))
        if detail.get("status") != "completed":
            return False   # genuinely still running — leave it
        stats = collect_run_results(
            db, client, cfg["owner"], cfg["repo"], int(run_id), cfg["artifact"], pipe.name,
        )
        _upsert_pipeline(
            db, pipe.id,
            status="pass" if detail.get("conclusion") == "success" else "fail",
            duration=_fmt_duration(_gh_run_seconds(detail)),
            run_id=(stats.get("run_ids") or [None])[-1],
        )
    return True


def _reconcile_gitlab(db, pipe, intg) -> bool:
    pid = pipe.id[len("gl-pipeline-"):]
    if not pid.isdigit():
        return False
    cfg = gitlab_ci_config(intg)
    with GitLabActionsClient(cfg["api_base"], cfg["token"]) as client:
        detail = client.get_pipeline(cfg["project"], int(pid))
        if detail.get("status") not in GITLAB_TERMINAL:
            return False
        stats = collect_pipeline_results(db, client, cfg["project"], int(pid), pipe.name)
        _upsert_pipeline(
            db, pipe.id,
            status="pass" if detail.get("status") == "success" else "fail",
            duration=_fmt_duration(detail.get("duration")),
            run_id=(stats.get("run_ids") or [None])[-1],
        )
    return True


def reconcile_running_pipelines(db) -> int:
    """Re-query the provider for every 'running' pipeline and finalize the ones
    that have actually finished. Returns the count updated."""
    running = db.query(models.Pipeline).filter(models.Pipeline.status == "running").all()
    updated = 0
    for pipe in running:
        if not pipe.integration_id:
            continue   # pushed via API without a source integration — can't re-query
        intg = db.query(models.Integration).filter(models.Integration.id == pipe.integration_id).first()
        if not intg:
            continue
        try:
            if pipe.platform == "github" and pipe.id.startswith("gh-run-"):
                updated += _reconcile_github(db, pipe, intg)
            elif pipe.platform == "gitlab" and pipe.id.startswith("gl-pipeline-"):
                updated += _reconcile_gitlab(db, pipe, intg)
        except Exception as e:
            logger.warning("reconcile of pipeline %s failed: %s", pipe.id, e)
    return updated


@router.post("/pipelines/reconcile")
def pipelines_reconcile(db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Poll the provider for any stuck 'running' pipelines and finalize them.
    Called by the pipelines page's live poll so rows self-heal. Returns the
    fresh pipeline list so the client can refresh in one round-trip."""
    updated = reconcile_running_pipelines(db)
    pipes = db.query(models.Pipeline).order_by(models.Pipeline.id).all()
    return {"updated": updated, "pipelines": [PipelineOut.model_validate(p) for p in pipes]}
