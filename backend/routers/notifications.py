from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from ..db import get_db
from .. import models
from ..auth_utils import require_role

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


class NotificationConfigOut(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    email_enabled: bool = False
    slack_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    notify_run_complete: bool = True
    notify_consecutive_fail: bool = True
    consecutive_fail_threshold: int = 3
    notify_comment: bool = True
    model_config = {"from_attributes": True}


class NotificationConfigIn(BaseModel):
    email_enabled: bool = False
    slack_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    smtp_from: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    notify_run_complete: bool = True
    notify_consecutive_fail: bool = True
    consecutive_fail_threshold: int = 3
    notify_comment: bool = True


# MUST come before /{notif_id} routes
@router.get("/config", response_model=NotificationConfigOut)
def get_config(current_user: models.User = ANY_ROLE, db: Session = Depends(get_db)):
    cfg = db.query(models.NotificationConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        return NotificationConfigOut()
    return cfg


@router.put("/config", response_model=NotificationConfigOut)
def put_config(payload: NotificationConfigIn, current_user: models.User = ANY_ROLE,
               db: Session = Depends(get_db)):
    cfg = db.query(models.NotificationConfig).filter_by(user_id=current_user.id).first()
    if not cfg:
        cfg = models.NotificationConfig(user_id=current_user.id)
        db.add(cfg)
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    return cfg


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
