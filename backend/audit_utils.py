"""
audit_utils.py — fire-and-forget audit log writer.

Creates its own SessionLocal per call so that:
- A failed audit write never rolls back the caller's business transaction.
- A business transaction rollback never swallows an audit record.

Usage:
    from .audit_utils import log_event, EVT_LOGIN_SUCCESS
    log_event(EVT_LOGIN_SUCCESS, actor_id=user.id, actor_email=user.email,
              description=f"{user.email} logged in successfully",
              ip_address=request.client.host)
"""
import sys
from datetime import datetime, timezone

from .db import SessionLocal
from . import models

# ---------------------------------------------------------------------------
# Event-type constants
# ---------------------------------------------------------------------------

# Auth events
EVT_LOGIN_SUCCESS        = "login_success"
EVT_LOGIN_FAIL           = "login_fail"
EVT_LOGOUT               = "logout"
EVT_PASSWORD_CHANGE      = "password_change"
EVT_PASSWORD_CHANGE_FAIL = "password_change_fail"
EVT_OAUTH_LINK           = "oauth_link"
EVT_OAUTH_UNLINK         = "oauth_unlink"
EVT_2FA_ENABLED          = "2fa_enabled"
EVT_2FA_DISABLED         = "2fa_disabled"
EVT_2FA_RECOVERY_USED    = "2fa_recovery_used"
EVT_2FA_CODES_REGEN      = "2fa_codes_regenerated"
EVT_2FA_FAIL             = "2fa_fail"

# User management events
EVT_USER_CREATED         = "user_created"
EVT_USER_DELETED         = "user_deleted"
EVT_ROLE_CHANGED         = "role_changed"

# Test events
EVT_TEST_CREATED         = "test_created"
EVT_TEST_UPDATED         = "test_updated"
EVT_TEST_DELETED         = "test_deleted"

# Run events
EVT_RUN_STARTED          = "run_started"
EVT_RUN_COMPLETED        = "run_completed"


# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------

def log_event(
    event_type: str,
    actor_email: str,
    description: str,
    actor_id: int | None = None,
    outcome: str = "success",
    ip_address: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    """Write one audit entry. Never raises — failures are logged to stderr only."""
    db = SessionLocal()
    try:
        entry = models.AuditLog(
            event_type=event_type,
            actor_id=actor_id,
            actor_email=actor_email,
            description=description,
            outcome=outcome,
            ip_address=ip_address,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            occurred_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        print(f"[audit] write failed: {exc}", file=sys.stderr)
    finally:
        db.close()
