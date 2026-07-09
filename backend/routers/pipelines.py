import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import PipelineOut, PipelineCreate
from ..auth_utils import get_current_user, require_role
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["pipelines"])

WRITE_ROLES = require_role("admin", "manager", "tester")


@router.get("/pipelines", response_model=List[PipelineOut])
def list_pipelines(
    response: Response,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return paginate(db.query(models.Pipeline).order_by(models.Pipeline.id), response, limit, offset)


@router.post("/pipelines", response_model=PipelineOut, status_code=201)
def upsert_pipeline(payload: PipelineCreate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Record a CI pipeline run. Intended for CI to push (typically with an API
    token): POST once with a `running` status at start, then POST again with the
    same `id` and the final `status`/`duration` at finish. Without an `id`, each
    call creates a new record."""
    existing = None
    if payload.id:
        existing = db.query(models.Pipeline).filter(models.Pipeline.id == payload.id).first()

    if existing:
        for field in ("name", "platform", "status", "duration", "commit", "author", "branch", "when", "url"):
            value = getattr(payload, field)
            if value is not None:
                setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    pipe = models.Pipeline(
        id=payload.id or f"wf-{uuid.uuid4().hex[:8]}",
        name=payload.name,
        platform=payload.platform,
        status=payload.status,
        duration=payload.duration,
        commit=payload.commit,
        author=payload.author,
        branch=payload.branch,
        when=payload.when or "just now",
        url=payload.url,
    )
    db.add(pipe)
    db.commit()
    db.refresh(pipe)
    return pipe


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Remove a pipeline run from the list (the run on the CI provider is untouched)."""
    pipe = db.query(models.Pipeline).filter(models.Pipeline.id == pipeline_id).first()
    if not pipe:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    db.delete(pipe)
    db.commit()
