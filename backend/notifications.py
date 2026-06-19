import asyncio
import json
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Dict, List
import httpx
from fastapi import WebSocket
from .db import SessionLocal
from . import models
from .webhook_utils import sign_payload


class NotificationManager:
    def __init__(self):
        self.connections: Dict[int, List[WebSocket]] = {}  # user_id → sockets

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        conns = self.connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)

    async def push(self, user_id: int, payload: dict):
        conns = self.connections.get(user_id, [])
        dead = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.remove(ws)


notif_manager = NotificationManager()


def _smtp_send_sync(host, port, user, password, msg):
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as s:
        s.starttls(context=context)
        if user and password:
            s.login(user, password)
        s.send_message(msg)


async def _send_email(cfg: models.NotificationConfig, to_email: str, notif: models.Notification):
    try:
        msg = MIMEText(f"{notif.title}\n\n{notif.link or ''}", "plain")
        msg["Subject"] = f"[ThoroTest] {notif.title}"
        msg["From"] = cfg.smtp_from or cfg.smtp_user or "noreply@thorotest"
        msg["To"] = to_email
        await asyncio.to_thread(
            _smtp_send_sync, cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_pass, msg
        )
    except Exception:
        pass  # Fire-and-forget


async def _send_slack(webhook_url: str, notif: models.Notification):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json={"text": f"*{notif.title}*\n{notif.link or ''}"},
                timeout=5,
            )
    except Exception:
        pass  # Fire-and-forget


async def _notify_run_events(run_id: str):
    """Called after run simulation completes. Creates Notification rows and fires delivery."""
    db = SessionLocal()
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            return

        now = datetime.now(timezone.utc).isoformat()

        # 1. run_complete: notify all users with notify_run_complete=True
        configs = db.query(models.NotificationConfig).filter_by(notify_run_complete=True).all()
        for cfg in configs:
            notif = models.Notification(
                user_id=cfg.user_id,
                event_type="run_complete",
                title=f"Run '{run.name}' {run.status}",
                link=f"#/runs/{run.id}",
                read=False,
                created_at=now,
            )
            db.add(notif)
            db.flush()  # get notif.id
            # WS push (non-blocking)
            asyncio.create_task(notif_manager.push(cfg.user_id, {
                "id": notif.id,
                "event_type": notif.event_type,
                "title": notif.title,
                "link": notif.link,
                "read": False,
                "created_at": notif.created_at,
            }))
            # Email delivery (fire-and-forget)
            if cfg.email_enabled and cfg.smtp_host:
                user = db.query(models.User).filter_by(id=cfg.user_id).first()
                if user and user.email:
                    asyncio.create_task(_send_email(cfg, user.email, notif))
            # Slack delivery (fire-and-forget)
            if cfg.slack_enabled and cfg.slack_webhook_url:
                asyncio.create_task(_send_slack(cfg.slack_webhook_url, notif))

        # 2. consecutive_fail: check each failed RunCase's test history
        failed_cases = db.query(models.RunCase).filter_by(run_id=run_id).all()
        notified_tests = set()  # deduplicate per test in this run
        for case in failed_cases:
            if case.status not in ("fail", "blocked"):
                continue
            if case.test_id in notified_tests:
                continue
            # Find users who have consecutive_fail enabled
            cfail_configs = db.query(models.NotificationConfig).filter_by(notify_consecutive_fail=True).all()
            for cfg in cfail_configs:
                threshold = cfg.consecutive_fail_threshold or 3
                recent = (
                    db.query(models.RunCase)
                    .filter(models.RunCase.test_id == case.test_id)
                    .order_by(models.RunCase.id.desc())
                    .limit(threshold)
                    .all()
                )
                if len(recent) == threshold and all(c.status in ("fail", "blocked") for c in recent):
                    test = db.query(models.Test).filter_by(id=case.test_id).first()
                    test_title = test.title if test else case.test_id
                    notif = models.Notification(
                        user_id=cfg.user_id,
                        event_type="consecutive_fail",
                        title=f"'{test_title}' failed {threshold}x in a row",
                        link=f"#/runs/{run_id}",
                        read=False,
                        created_at=now,
                    )
                    db.add(notif)
                    db.flush()
                    asyncio.create_task(notif_manager.push(cfg.user_id, {
                        "id": notif.id,
                        "event_type": notif.event_type,
                        "title": notif.title,
                        "link": notif.link,
                        "read": False,
                        "created_at": notif.created_at,
                    }))
            notified_tests.add(case.test_id)

        db.commit()
    except Exception:
        pass  # Background task — swallow errors silently
    finally:
        db.close()


async def _fire_webhooks(run_id: str):
    """Deliver a signed run.completed payload to all active subscribed webhooks."""
    db = SessionLocal()
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            return
        webhooks = (
            db.query(models.Webhook)
            .filter(models.Webhook.status == "active")
            .all()
        )
        targets = [w for w in webhooks if "run.completed" in (w.events or [])]
        if not targets:
            return
        payload = {
            "event": "run.completed",
            "source": "thorotest",
            "run_id": run.id,
            "name": run.name,
            "status": run.status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        now_label = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        for wh in targets:
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
            wh.last_status_code = status_code
            wh.last_delivery_at = now_label
        db.commit()
    except Exception:
        pass  # fire-and-forget background task
    finally:
        db.close()


async def _notify_comment_event(test_id: str, commenter_username: str):
    """Called after a comment is posted. Notifies all users with notify_comment=True."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).isoformat()
        test = db.query(models.Test).filter_by(id=test_id).first()
        test_title = test.title if test else test_id

        configs = db.query(models.NotificationConfig).filter_by(notify_comment=True).all()
        for cfg in configs:
            notif = models.Notification(
                user_id=cfg.user_id,
                event_type="comment",
                title=f"{commenter_username} commented on '{test_title}'",
                link=f"#/tests/{test_id}",
                read=False,
                created_at=now,
            )
            db.add(notif)
            db.flush()
            asyncio.create_task(notif_manager.push(cfg.user_id, {
                "id": notif.id,
                "event_type": notif.event_type,
                "title": notif.title,
                "link": notif.link,
                "read": False,
                "created_at": notif.created_at,
            }))
            if cfg.email_enabled and cfg.smtp_host:
                user = db.query(models.User).filter_by(id=cfg.user_id).first()
                if user and user.email:
                    asyncio.create_task(_send_email(cfg, user.email, notif))
            if cfg.slack_enabled and cfg.slack_webhook_url:
                asyncio.create_task(_send_slack(cfg.slack_webhook_url, notif))

        db.commit()
    except Exception:
        pass
    finally:
        db.close()
