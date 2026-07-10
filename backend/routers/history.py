"""
history.py — read-only per-record change history.
GET /api/history/{entity_type}/{entity_id} — any authenticated user.
Returns field-level who/when/what entries, newest first.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth_utils import get_current_user

router = APIRouter(tags=["history"])

_ALLOWED = {"test", "requirement", "defect"}


@router.get("/history/{entity_type}/{entity_id}")
def get_record_history(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    if entity_type not in _ALLOWED:
        raise HTTPException(status_code=404, detail="Unknown entity type")
    rows = (
        db.query(models.RecordHistory)
        .filter(
            models.RecordHistory.entity_type == entity_type,
            models.RecordHistory.entity_id == str(entity_id),
        )
        .order_by(models.RecordHistory.created_at.desc(), models.RecordHistory.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "action": r.action,
            "actor_name": r.actor_name,
            "changes": r.changes or [],
            "created_at": r.created_at,
        }
        for r in rows
    ]
