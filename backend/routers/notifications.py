from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..db import get_db
from .. import models
from ..auth_utils import require_role
from ..net_guard import assert_public_http_url, UnsafeURLError

router = APIRouter(prefix="/notifications", tags=["notifications"])

ANY_ROLE = require_role("admin", "manager", "tester", "viewer")


class NotificationOut(BaseModel):
    id: int
    user_id: int
    event_type: str
    title: str
    link: Optional[str] = None
    read: bool
    created_at: str
    model_config = {"from_attributes": True}


# Per-user SMTP settings are deliberately NOT part of this API (SECURITY H-1).
# They let any authenticated user point the server at an arbitrary host:port,
# and stored a relay password in plaintext that GET echoed straight back.
# Outbound mail now goes through the operator-configured relay in
# backend/emailer.py (SMTP_HOST etc). The columns remain on the model only so
# existing rows are not dropped; nothing reads or writes them.
class NotificationConfigOut(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    email_enabled: bool = False
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = None
    # Whether the operator has configured a relay, so the UI can explain why
    # enabling email does nothing on an instance without one.
    email_available: bool = False
    notify_run_complete: bool = True
    notify_consecutive_fail: bool = True
    consecutive_fail_threshold: int = 3
    notify_comment: bool = True
    notify_mention: bool = True
    notify_assigned: bool = True
    model_config = {"from_attributes": True}


class NotificationConfigIn(BaseModel):
    email_enabled: bool = False
    slack_enabled: bool = False
    slack_webhook_url: Optional[str] = None
    notify_run_complete: bool = True
    notify_consecutive_fail: bool = True
    consecutive_fail_threshold: int = 3
    notify_comment: bool = True
    notify_mention: bool = True
    notify_assigned: bool = True


def _as_config_out(cfg: models.NotificationConfig | None) -> NotificationConfigOut:
    from .. import emailer

    out = NotificationConfigOut() if cfg is None else NotificationConfigOut.model_validate(cfg)
    out.email_available = emailer.is_configured()
    return out


# MUST come before /{notif_id} routes
@router.get("/config", response_model=NotificationConfigOut)
def get_config(current_user: models.User = ANY_ROLE, db: Session = Depends(get_db)):
    cfg = db.query(models.NotificationConfig).filter_by(user_id=current_user.id).first()
    return _as_config_out(cfg)


@router.put("/config", response_model=NotificationConfigOut)
def put_config(payload: NotificationConfigIn, current_user: models.User = ANY_ROLE,
               db: Session = Depends(get_db)):
    # The server will POST to this URL on run/comment events, so it is an
    # outbound-request primitive and gets the same SSRF guard as webhooks.
    # resolve=False here (fail fast without a DNS dependency); the delivery path
    # re-checks with full resolution, which also covers a host re-pointed later.
    if payload.slack_webhook_url:
        try:
            assert_public_http_url(payload.slack_webhook_url, resolve=False)
        except UnsafeURLError as e:
            raise HTTPException(status_code=422, detail=f"Unsafe Slack webhook URL: {e}")

    cfg = db.query(models.NotificationConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        cfg = models.NotificationConfig(user_id=current_user.id)
        db.add(cfg)
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return _as_config_out(cfg)


@router.get("", response_model=List[NotificationOut])
def list_notifications(limit: int = 20, current_user: models.User = ANY_ROLE,
                       db: Session = Depends(get_db)):
    return (
        db.query(models.Notification)
        .filter_by(user_id=current_user.id)
        .order_by(models.Notification.id.desc())
        .limit(limit)
        .all()
    )


@router.post("/mark-all-read")
def mark_all_read(current_user: models.User = ANY_ROLE, db: Session = Depends(get_db)):
    db.query(models.Notification).filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.commit()
    return {"ok": True}


@router.patch("/{notif_id}/read", response_model=NotificationOut)
def mark_read(notif_id: int, current_user: models.User = ANY_ROLE, db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter_by(id=notif_id, user_id=current_user.id).first()
    if not n:
        raise HTTPException(404)
    n.read = True
    db.commit()
    db.refresh(n)
    return n


@router.delete("/{notif_id}", status_code=204)
def delete_notification(notif_id: int, current_user: models.User = ANY_ROLE,
                        db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter_by(id=notif_id, user_id=current_user.id).first()
    if not n:
        raise HTTPException(404)
    db.delete(n)
    db.commit()
