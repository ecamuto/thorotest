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

logger = logging.getLogger("thorotest.ci")
router = APIRouter(tags=["ci"])

WRITE_ROLES = require_role("admin", "manager")

POLL_INTERVAL = 15      # seconds between GitHub polls
FIND_TIMEOUT = 120      # seconds to locate the dispatched run
RUN_TIMEOUT = 1800      # seconds to wait for the run to complete

# In-memory registry of dispatch jobs (per-process; lost on restart).
_JOBS: dict[str, dict] = {}


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
    """Dispatch a workflow and start collecting its results in the background."""
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")

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
