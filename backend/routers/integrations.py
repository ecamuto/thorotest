from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import IntegrationOut, IntegrationCreate, IntegrationUpdate
from ..auth_utils import require_role, get_current_user
from ..github_sync import sync_integration
from ..gitlab_sync import sync_integration as sync_gitlab_integration, parse_gitlab_repo
from ..jira_sync import sync_jira_requirements, normalize_base_url
from ..net_guard import assert_public_http_url, UnsafeURLError
from ..vcs import detect_provider

router = APIRouter(tags=["integrations"])

WRITE_ROLES = require_role("admin", "manager")


def _assert_safe_outbound_urls(intg_type: str, config: dict) -> None:
    """Fail fast (422) when a config points outbound HTTP at a non-public host
    (SECURITY M-1 / roadmap S-8). The sync/push clients re-check at use time;
    this surfaces the error at save instead of at the next sync.

    GitHub needs no check: its client always calls the fixed api.github.com.
    """
    config = config or {}
    try:
        if intg_type == "jira":
            if config.get("base_url"):
                assert_public_http_url(normalize_base_url(config["base_url"]), resolve=False)
        elif config.get("repo_url") or config.get("api_base"):
            try:
                provider = detect_provider(config)
            except ValueError:
                return  # provider undetectable — sync will reject with its own error
            if provider == "gitlab":
                api_base, _ = parse_gitlab_repo(config.get("repo_url") or "",
                                                config.get("api_base"))
                assert_public_http_url(api_base, resolve=False)
    except (UnsafeURLError, ValueError) as e:
        raise HTTPException(status_code=422, detail=f"Unsafe integration URL: {e}")


@router.get("/integrations", response_model=List[IntegrationOut])
def list_integrations(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return db.query(models.Integration).all()


@router.post("/integrations", response_model=IntegrationOut, status_code=201)
def create_integration(payload: IntegrationCreate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    existing = db.query(models.Integration).filter(models.Integration.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Integration ID already exists")
    _assert_safe_outbound_urls(payload.type, payload.config or {})
    intg = models.Integration(**payload.model_dump())
    db.add(intg)
    db.commit()
    db.refresh(intg)
    return intg


@router.patch("/integrations/{intg_id}", response_model=IntegrationOut)
def update_integration(intg_id: str, payload: IntegrationUpdate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    updates = payload.model_dump(exclude_unset=True)
    if "config" in updates and updates["config"] is not None:
        # Merge so a redacted/empty secret from the client never wipes the stored one.
        merged = dict(intg.config or {})
        incoming = updates.pop("config")
        prev = intg.config or {}
        merged.update(incoming)
        # Preserve stored secrets when the client submits them blank (redacted).
        for secret_key in ("token", "api_token"):
            if not incoming.get(secret_key):
                if prev.get(secret_key):
                    merged[secret_key] = prev[secret_key]
                else:
                    merged.pop(secret_key, None)
        merged.pop("token_set", None)
        merged.pop("api_token_set", None)
        _assert_safe_outbound_urls(updates.get("type") or intg.type, merged)
        intg.config = merged
    for field, value in updates.items():
        setattr(intg, field, value)
    db.commit()
    db.refresh(intg)
    return intg


def _sync_provider(intg: models.Integration) -> str:
    if intg.type == "jira":
        return "jira"
    return detect_provider(intg.config or {})


def enqueue_sync_job(db: Session, intg: models.Integration) -> models.CIJob:
    """Create, or coalesce onto, one active durable sync per integration."""
    active = db.query(models.CIJob).filter(
        models.CIJob.integration_id == intg.id,
        models.CIJob.job_type == "integration_sync",
        models.CIJob.queue_status.in_(("queued", "processing")),
    ).order_by(models.CIJob.started_at.desc()).first()
    if active:
        return active

    provider = _sync_provider(intg)
    now = datetime.now(timezone.utc).isoformat()
    job = models.CIJob(
        id=uuid.uuid4().hex[:12],
        job_type="integration_sync",
        integration_id=intg.id,
        provider=provider,
        workflow="sync",
        ref="",
        status="queued",
        queue_status="queued",
        started_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    return job


def execute_sync_job(job_id: str, worker_id: str | None = None) -> None:
    """Execute one leased provider-sync job outside the HTTP request path."""
    from .ci import LostJobLease, _update_job
    from ..db import SessionLocal

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
            raise LostJobLease(f"provider sync job {job_id} lease is no longer owned")
        intg = db.query(models.Integration).filter(
            models.Integration.id == job.integration_id
        ).first()
        if not intg:
            raise RuntimeError("integration was deleted")

        _update_job(job_id, worker_id=worker_id, status="syncing")
        try:
            if intg.type == "jira":
                stats = sync_jira_requirements(db, intg)
            elif job.provider == "gitlab":
                stats = sync_gitlab_integration(db, intg)
            else:
                stats = sync_integration(db, intg)
        except Exception:
            intg.status = "error"
            db.commit()
            raise
        intg.status = "active"
        db.commit()
        stats = {"last_sync": intg.last_sync, **stats}
    finally:
        db.close()

    _update_job(job_id, worker_id=worker_id, status="done", result=stats)


@router.post("/integrations/{intg_id}/sync", status_code=202)
def enqueue_integration_sync(intg_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Queue a recoverable GitHub/GitLab/Jira sync and return immediately."""
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        job = enqueue_sync_job(db, intg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job.id, "job_type": job.job_type, "status": job.status}


@router.delete("/integrations/{intg_id}", status_code=204)
def delete_integration(intg_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    db.delete(intg)
    db.commit()
