"""Outbound system email (password resets, future account mail).

Configured via environment — system mail must work before any user has
logged in, so it does not use the per-user NotificationConfig SMTP fields:

    SMTP_HOST=smtp.example.com     (required to enable sending)
    SMTP_PORT=587                  (default 587; 465 switches to implicit TLS)
    SMTP_USER= / SMTP_PASS=        (optional — omit for unauthenticated relays)
    SMTP_FROM=noreply@example.com  (default: SMTP_USER, then noreply@localhost)
    SMTP_STARTTLS=1                (default on for port 587; set 0 to disable)

When SMTP_HOST is unset, send_email() logs and returns False — callers treat
email as best-effort and must not leak delivery status to API clients.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger("thorotest.email")


def is_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip())


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on accepted delivery, False otherwise.

    Synchronous (smtplib) — call from a background task, not a request handler.
    """
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        logger.warning("SMTP_HOST not configured — dropping email to %s (%s)", to, subject)
        return False
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "")
    sender = os.getenv("SMTP_FROM", "").strip() or user or "noreply@localhost"
    starttls = os.getenv("SMTP_STARTTLS", "1").strip().lower() not in ("0", "false", "no")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                if starttls:
                    s.starttls(context=ssl.create_default_context())
                if user:
                    s.login(user, password)
                s.send_message(msg)
        logger.info("Sent email to %s: %s", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s (%s)", to, subject)
        return False
