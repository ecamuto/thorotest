import json
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import WebhookOut, WebhookCreate, WebhookUpdate, WebhookCreated
from ..webhook_utils import generate_secret, sign_payload

router = APIRouter(tags=["webhooks"])


@router.get("/webhooks", response_model=List[WebhookOut])
def list_webhooks(db: Session = Depends(get_db)):
    return db.query(models.Webhook).all()


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
def create_webhook(payload: WebhookCreate, db: Session = Depends(get_db)):
    secret = generate_secret()
    wh = models.Webhook(url=payload.url, events=payload.events, hmac_secret=secret)
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return WebhookCreated(
        id=wh.id, url=wh.url, events=wh.events, status=wh.status,
        last_status_code=wh.last_status_code, last_delivery_at=wh.last_delivery_at,
        secret=secret,
    )


@router.patch("/webhooks/{wh_id}", response_model=WebhookOut)
def update_webhook(wh_id: int, payload: WebhookUpdate, db: Session = Depends(get_db)):
    wh = db.query(models.Webhook).filter(models.Webhook.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(wh, field, value)
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/webhooks/{wh_id}", status_code=204)
def delete_webhook(wh_id: int, db: Session = Depends(get_db)):
    wh = db.query(models.Webhook).filter(models.Webhook.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(wh)
    db.commit()


@router.post("/webhooks/{wh_id}/regenerate-secret", response_model=WebhookCreated)
def regenerate_webhook_secret(wh_id: int, db: Session = Depends(get_db)):
    wh = db.query(models.Webhook).filter(models.Webhook.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    secret = generate_secret()
    wh.hmac_secret = secret
    db.commit()
    db.refresh(wh)
    return WebhookCreated(
        id=wh.id, url=wh.url, events=wh.events, status=wh.status,
        last_status_code=wh.last_status_code, last_delivery_at=wh.last_delivery_at,
        secret=secret,
    )


@router.post("/webhooks/{wh_id}/test")
async def test_webhook(wh_id: int, db: Session = Depends(get_db)):
    wh = db.query(models.Webhook).filter(models.Webhook.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    payload = {
        "event": "test",
        "source": "thorotest",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if wh.hmac_secret:
        headers["X-Hub-Signature-256"] = sign_payload(body_bytes, wh.hmac_secret)
    status_code = 0
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(wh.url, content=body_bytes, headers=headers)
            status_code = r.status_code
    except Exception:
        status_code = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    wh.last_status_code = status_code
    wh.last_delivery_at = now
    db.commit()
    db.refresh(wh)
    return {"status_code": status_code, "ok": 200 <= status_code < 300}
