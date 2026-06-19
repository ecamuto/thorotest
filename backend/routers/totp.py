"""
totp.py — 2FA endpoints.

Plan 15-01: POST /auth/login/2fa  — complete the 2FA login step
Plan 15-02: GET /me/2fa/setup, POST /me/2fa/enable, DELETE /me/2fa/disable,
            POST /me/2fa/recovery-codes/regenerate, GET /me/2fa/recovery-codes/count
"""
from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..schemas import (
    TwoFALoginPayload,
    TwoFAEnablePayload,
    TwoFADisablePayload,
    TwoFARegeneratePayload,
)
from ..auth_utils import create_access_token, get_current_user
from ..audit_utils import (
    log_event,
    EVT_LOGIN_SUCCESS,
    EVT_2FA_RECOVERY_USED,
    EVT_2FA_ENABLED,
    EVT_2FA_DISABLED,
    EVT_2FA_CODES_REGEN,
    EVT_2FA_FAIL,
)
from ..totp_utils import (
    decode_partial_token,
    verify_totp_code,
    verify_recovery_code,
    check_2fa_rate,
    record_2fa_failure,
    generate_totp_setup,
    encrypt_totp_secret,
    generate_recovery_codes,
)

router = APIRouter(tags=["totp"])


def _user_dict(user: models.User) -> dict:
    """Return the standard user dict shape (same as auth.login)."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "language": user.language or "en",
    }


@router.post("/auth/login/2fa")
def complete_2fa_login(
    request: Request,
    payload: TwoFALoginPayload,
    db: Session = Depends(get_db),
):
    """
    Complete the 2FA login step.

    Accepts a partial_token (scope=2fa_pending) plus a 6-digit TOTP code
    or a 9-char recovery code (xxxx-xxxx). On success, issues a full JWT.

    - Full session tokens are rejected (decode_partial_token enforces scope).
    - Rate-limited to 5 failed attempts per 30 seconds per user.
    - Recovery codes are single-use; used=True is committed before returning.
    - TOTP and recovery failures both return the same generic "Invalid code" (no oracle).
    """
    ip = request.client.host if request.client else None

    # Validate partial token (raises 401 for wrong scope or expired JWT)
    user_id = decode_partial_token(payload.partial_token)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.totp_enabled:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Rate limit check (read only — failure recorded below on bad code)
    allowed, retry_after = check_2fa_rate(user_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many attempts. Try again in {retry_after}s",
        )

    code = payload.code.strip()

    # Auto-detect: 9-char format with dash = recovery code, otherwise TOTP
    if len(code) == 9 and "-" in code:
        # Recovery code branch
        recovery_rows = (
            db.query(models.TotpRecoveryCode)
            .filter_by(user_id=user_id, used=False)
            .with_for_update()
            .all()
        )
        matched = verify_recovery_code(code, recovery_rows)
        if not matched:
            record_2fa_failure(user_id)
            log_event(
                EVT_2FA_FAIL,
                actor_id=user.id,
                actor_email=user.email,
                description=f"{user.email} failed 2FA login (recovery code)",
                outcome="fail",
                ip_address=ip,
            )
            raise HTTPException(status_code=400, detail="Invalid code")
        # Mark used and commit before returning (atomic single-use)
        matched.used = True
        db.commit()
        log_event(
            EVT_2FA_RECOVERY_USED,
            actor_id=user.id,
            actor_email=user.email,
            description=f"{user.email} logged in with a recovery code",
            ip_address=ip,
        )
    else:
        # TOTP branch
        if not verify_totp_code(user.totp_secret, code):
            record_2fa_failure(user_id)
            log_event(
                EVT_2FA_FAIL,
                actor_id=user.id,
                actor_email=user.email,
                description=f"{user.email} failed 2FA login (TOTP code)",
                outcome="fail",
                ip_address=ip,
            )
            raise HTTPException(status_code=400, detail="Invalid code")

    # Issue full JWT
    log_event(
        EVT_LOGIN_SUCCESS,
        actor_id=user.id,
        actor_email=user.email,
        description=f"{user.email} completed 2FA login",
        ip_address=ip,
    )
    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": _user_dict(user),
    }


# ---------------------------------------------------------------------------
# Enrollment: GET /me/2fa/setup — generate QR + secret (no persistence)
# ---------------------------------------------------------------------------

@router.get("/me/2fa/setup")
def get_2fa_setup(
    current_user: models.User = Depends(get_current_user),
):
    """
    Generate a fresh TOTP secret and QR code for enrollment.

    The secret is NOT stored server-side — the frontend must submit it back
    in POST /me/2fa/enable (pending_secret) so we can verify before persisting.
    """
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")
    return generate_totp_setup(current_user.email)


# ---------------------------------------------------------------------------
# Enrollment: POST /me/2fa/enable — verify TOTP before activating
# ---------------------------------------------------------------------------

@router.post("/me/2fa/enable")
def enable_2fa(
    payload: TwoFAEnablePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify the TOTP code for the pending (not-yet-stored) secret, then activate 2FA.

    On success: stores Fernet-encrypted secret, sets totp_enabled=True, inserts 10
    hashed recovery codes, and returns the 10 plaintext codes for one-time display.
    On failure: returns 400; user.totp_enabled remains False.
    """
    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA already enabled")

    # Verify code against the PENDING (plaintext) secret — not encrypted yet
    if not pyotp.TOTP(payload.pending_secret).verify(payload.totp_code, valid_window=1):
        raise HTTPException(
            status_code=400,
            detail="Invalid TOTP code — check your authenticator app clock",
        )

    # Persist encrypted secret and enable 2FA
    current_user.totp_secret = encrypt_totp_secret(payload.pending_secret)
    current_user.totp_enabled = True

    # Generate and insert 10 hashed recovery codes
    now = datetime.now(timezone.utc).isoformat()
    code_pairs = generate_recovery_codes()
    for _, code_hash in code_pairs:
        db.add(models.TotpRecoveryCode(
            user_id=current_user.id,
            code_hash=code_hash,
            used=False,
            created_at=now,
        ))
    db.commit()

    log_event(
        EVT_2FA_ENABLED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} enabled 2FA",
    )

    return {"recovery_codes": [plain for plain, _ in code_pairs]}


# ---------------------------------------------------------------------------
# Disable: DELETE /me/2fa/disable — TOTP-gated full state clear
# ---------------------------------------------------------------------------

@router.delete("/me/2fa/disable")
def disable_2fa(
    payload: TwoFADisablePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disable 2FA after verifying the current TOTP code.

    Atomically clears totp_secret, sets totp_enabled=False, and deletes all
    recovery codes for the user. A wrong code leaves 2FA active.
    """
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")

    if not verify_totp_code(current_user.totp_secret, payload.totp_code):
        raise HTTPException(status_code=400, detail="Invalid code")

    # Atomic clear
    current_user.totp_secret = None
    current_user.totp_enabled = False
    db.query(models.TotpRecoveryCode).filter_by(user_id=current_user.id).delete()
    db.commit()

    log_event(
        EVT_2FA_DISABLED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} disabled 2FA",
    )

    return {"ok": True}


# ---------------------------------------------------------------------------
# Regenerate: POST /me/2fa/recovery-codes/regenerate
# ---------------------------------------------------------------------------

@router.post("/me/2fa/recovery-codes/regenerate")
def regenerate_recovery_codes(
    payload: TwoFARegeneratePayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Replace all recovery codes with a fresh set, after TOTP verification.

    Old codes are deleted atomically before inserting 10 new hashed codes.
    Returns the 10 new plaintext codes for one-time display.
    """
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA not enabled")

    if not verify_totp_code(current_user.totp_secret, payload.totp_code):
        raise HTTPException(status_code=400, detail="Invalid code")

    # Delete old codes and insert fresh set
    db.query(models.TotpRecoveryCode).filter_by(user_id=current_user.id).delete()
    now = datetime.now(timezone.utc).isoformat()
    code_pairs = generate_recovery_codes()
    for _, code_hash in code_pairs:
        db.add(models.TotpRecoveryCode(
            user_id=current_user.id,
            code_hash=code_hash,
            used=False,
            created_at=now,
        ))
    db.commit()

    log_event(
        EVT_2FA_CODES_REGEN,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} regenerated 2FA recovery codes",
    )

    return {"recovery_codes": [plain for plain, _ in code_pairs]}


# ---------------------------------------------------------------------------
# Count: GET /me/2fa/recovery-codes/count
# ---------------------------------------------------------------------------

@router.get("/me/2fa/recovery-codes/count")
def recovery_codes_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the number of unused recovery codes and 2FA status.

    Used by the SecurityTab to render the 'N codes remaining' / low-codes warning.
    """
    remaining = (
        db.query(models.TotpRecoveryCode)
        .filter_by(user_id=current_user.id, used=False)
        .count()
    )
    return {"remaining": remaining, "enabled": current_user.totp_enabled}
