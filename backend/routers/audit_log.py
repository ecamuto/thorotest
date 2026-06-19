"""
audit_log.py — read-only audit log endpoint.
GET /api/audit-log — admin and manager only; supports date-range filter + pagination.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth_utils import require_role

router = APIRouter(tags=["audit"])

AUDIT_ROLES = require_role("admin", "manager")


@router.get("/audit-log")
def get_audit_log(
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: models.User = AUDIT_ROLES,
):
    """
    Return paginated audit log entries, newest first.

    Query params:
      start_date  YYYY-MM-DD  inclusive start (UTC)
      end_date    YYYY-MM-DD  inclusive end (through end of day)
      page        1-based page number (default 1)
      page_size   entries per page (default 50)
    """
    q = db.query(models.AuditLog).order_by(models.AuditLog.occurred_at.desc())

    if start_date:
        # ISO string comparison: "2026-06-11" < "2026-06-11T00:00:00Z" so append T00:00:00Z
        q = q.filter(models.AuditLog.occurred_at >= start_date + "T00:00:00Z")

    if end_date:
        # Inclusive through end of day — append T23:59:59.999999Z
        q = q.filter(models.AuditLog.occurred_at <= end_date + "T23:59:59.999999Z")

    total = q.count()
    entries = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "entries": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "actor_email": e.actor_email,
                "description": e.description,
                "outcome": e.outcome,
                "ip_address": e.ip_address,
                "target_type": e.target_type,
                "target_id": e.target_id,
                "occurred_at": e.occurred_at,
            }
            for e in entries
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
