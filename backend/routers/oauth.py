"""
oauth.py — GitHub (and shared) OAuth Authorization Code flow.

Endpoints:
  GET  /auth/oauth/github/redirect       — initiate GitHub OAuth
  GET  /auth/oauth/github/callback       — handle GitHub OAuth callback
  POST /auth/oauth/confirm-link          — confirm same-email account link with password

Shared logic:
  upsert_oauth_user()  — new-user provisioning / link-required gate / returning-user login
"""

import os
import re
import secrets
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth_utils import create_access_token, verify_password
from ..audit_utils import (
    log_event,
    EVT_LOGIN_SUCCESS,
    EVT_USER_CREATED,
    EVT_OAUTH_LINK,
)

router = APIRouter(tags=["oauth"])

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.getenv("TESTHUB_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# State nonce helpers (CSRF protection)
# ---------------------------------------------------------------------------

def _new_state(db: Session, provider: str) -> str:
    """Generate a single-use OAuth state nonce, valid for 10 minutes."""
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.add(models.OAuthState(
        state_token=token,
        provider=provider,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    ))
    db.commit()
    return token


def _consume_state(db: Session, state: str, provider: str) -> None:
    """Validate and delete a state nonce. Raises HTTP 400 if invalid or expired."""
    now = datetime.now(timezone.utc).isoformat()
    row = db.query(models.OAuthState).filter(
        models.OAuthState.state_token == state,
        models.OAuthState.provider == provider,
        models.OAuthState.expires_at > now,
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Username derivation
# ---------------------------------------------------------------------------

def _derive_username(base: str, db: Session) -> str:
    """Slugify base and find a unique username, appending _N or random hex on collision."""
    slug = re.sub(r"\W+", "_", base).strip("_").lower()[:28] or "user"
    candidate = slug
    for i in range(2, 20):
        if not db.query(models.User).filter(models.User.username == candidate).first():
            return candidate
        candidate = f"{slug}_{i}"
    return f"{slug}_{secrets.token_hex(4)}"


# ---------------------------------------------------------------------------
# User dict helper (mirrors auth.py login response shape)
# ---------------------------------------------------------------------------

def _user_dict(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "language": user.language or "en",
        "totp_enabled": user.totp_enabled,
    }


# ---------------------------------------------------------------------------
# Core shared logic
# ---------------------------------------------------------------------------

def issue_session_or_2fa(user: models.User, ip: str | None) -> dict:
    """
    Uniform 2FA chokepoint for OAuth session issuance.
    If the user has TOTP enabled, return a 2fa_required partial-token response
    (same shape/semantics as auth.py:57-60). Otherwise issue a full session.
    Returns the {"status": "ok", "token": ...} shape used by upsert_oauth_user.
    """
    if user.totp_enabled:
        from ..totp_utils import create_partial_token
        return {"status": "2fa_required", "partial_token": create_partial_token(user.id)}
    return {"status": "ok", "token": create_access_token(user.id), "user": _user_dict(user)}


def upsert_oauth_user(
    db: Session,
    provider: str,
    oauth_id: str | int,
    email: str | None,
    verified: bool,
    display_name: str | None,
    ip: str | None,
) -> dict:
    """
    Shared OAuth user resolution logic for all providers.

    Returns one of:
      {"status": "ok",            "token": <jwt>, "user": <dict>}
      {"status": "link_required", "pending_token": <str>}

    Raises HTTP 400 for missing/unverified email.
    """
    # 1. Email required
    if not email:
        raise HTTPException(
            status_code=400,
            detail="We need a verified email from the provider to continue.",
        )
    # 2. Email must be verified
    if not verified:
        raise HTTPException(
            status_code=400,
            detail="Your provider email must be verified to continue.",
        )

    oauth_id_str = str(oauth_id)

    # 3. Returning OAuth user — identity already linked
    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == provider,
        models.OAuthIdentity.oauth_id == oauth_id_str,
    ).first()
    if identity:
        user = db.query(models.User).filter(models.User.id == identity.user_id).first()
        log_event(
            EVT_LOGIN_SUCCESS,
            actor_id=user.id,
            actor_email=user.email,
            description=f"{user.email} logged in via {provider} OAuth",
            ip_address=ip,
        )
        return issue_session_or_2fa(user, ip)

    # 4. Same-email match — require explicit confirmation
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        now = datetime.now(timezone.utc)
        pending_token = secrets.token_urlsafe(32)
        pending = models.OAuthPendingLink(
            state_token=pending_token,
            provider=provider,
            oauth_id=oauth_id_str,
            email=email,
            display_name=display_name,
            user_id=existing.id,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=20)).isoformat(),
        )
        db.add(pending)
        db.commit()
        return {"status": "link_required", "pending_token": pending_token}

    # 5. New user — provision with viewer role
    now = datetime.now(timezone.utc)
    username = _derive_username(display_name or email.split("@")[0], db)
    user = models.User(
        username=username,
        email=email,
        hashed_password="!",          # sentinel — OAuth-only accounts cannot use local login
        display_name=display_name,
        role="viewer",
    )
    db.add(user)
    db.flush()   # get user.id before creating identity

    identity = models.OAuthIdentity(
        user_id=user.id,
        provider=provider,
        oauth_id=oauth_id_str,
        email=email,
        created_at=now.isoformat(),
    )
    db.add(identity)
    db.commit()
    db.refresh(user)

    log_event(
        EVT_USER_CREATED,
        actor_id=user.id,
        actor_email=user.email,
        description=f"OAuth new user created via {provider}: {user.email}",
    )
    log_event(
        EVT_LOGIN_SUCCESS,
        actor_id=user.id,
        actor_email=user.email,
        description=f"{user.email} logged in via {provider} OAuth",
        ip_address=ip,
    )
    return issue_session_or_2fa(user, ip)


# ---------------------------------------------------------------------------
# GitHub redirect
# ---------------------------------------------------------------------------

@router.get("/auth/oauth/github/redirect")
async def github_redirect(db: Session = Depends(get_db)):
    """Initiate the GitHub OAuth Authorization Code flow."""
    state = _new_state(db, "github")
    params = urlencode({
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/api/auth/oauth/github/callback",
        "scope": "user:email",
        "state": state,
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


# ---------------------------------------------------------------------------
# GitHub callback
# ---------------------------------------------------------------------------

@router.get("/auth/oauth/github/callback")
async def github_callback(
    db: Session = Depends(get_db),
    code: str = None,
    state: str = None,
    error: str = None,
    request: Request = None,
):
    """Handle the GitHub OAuth callback after user authorization."""
    # User denied consent
    if error:
        return RedirectResponse(f"{BASE_URL}/#oauth-error=cancelled&provider=github")

    # Validate state nonce
    try:
        _consume_state(db, state, "github")
    except HTTPException:
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=github")

    try:
        redirect_uri = f"{BASE_URL}/api/auth/oauth/github/callback"

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            print(f"[oauth/github] token exchange failed: {token_data}", file=sys.stderr)
            return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=github")

        github_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Fetch emails and user profile in parallel
        async with httpx.AsyncClient() as client:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers=github_headers,
            )
            user_resp = await client.get(
                "https://api.github.com/user",
                headers=github_headers,
            )

        emails_data = emails_resp.json()
        user_json = user_resp.json()

        # Find primary+verified email (always use /user/emails — /user.email may be null)
        primary_email_obj = next(
            (e for e in emails_data if e.get("primary") and e.get("verified")), None
        )
        primary_email = primary_email_obj["email"] if primary_email_obj else None

        display_name = user_json.get("name") or user_json.get("login")

    except Exception as exc:
        print(f"[oauth/github] network/parse error: {exc}", file=sys.stderr)
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=github")

    ip = request.client.host if request and request.client else None

    # upsert_oauth_user may raise HTTPException for unverified/missing email
    try:
        result = upsert_oauth_user(
            db,
            provider="github",
            oauth_id=user_json["id"],
            email=primary_email,
            verified=bool(primary_email_obj),
            display_name=display_name,
            ip=ip,
        )
    except HTTPException as exc:
        print(f"[oauth/github] upsert rejected: {exc.detail}", file=sys.stderr)
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=github")

    if result["status"] == "2fa_required":
        return RedirectResponse(f"{BASE_URL}/#oauth-2fa={result['partial_token']}")
    elif result["status"] == "ok":
        return RedirectResponse(f"{BASE_URL}/#token={result['token']}")
    else:
        return RedirectResponse(f"{BASE_URL}/#oauth-confirm={result['pending_token']}")


# ---------------------------------------------------------------------------
# Google redirect
# ---------------------------------------------------------------------------

@router.get("/auth/oauth/google/redirect")
async def google_redirect(db: Session = Depends(get_db)):
    """Initiate the Google OAuth Authorization Code flow."""
    state = _new_state(db, "google")
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{BASE_URL}/api/auth/oauth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


# ---------------------------------------------------------------------------
# Google callback
# ---------------------------------------------------------------------------

@router.get("/auth/oauth/google/callback")
async def google_callback(
    db: Session = Depends(get_db),
    code: str = None,
    state: str = None,
    error: str = None,
    request: Request = None,
):
    """Handle the Google OAuth callback after user authorization."""
    # User denied consent
    if error:
        return RedirectResponse(f"{BASE_URL}/#oauth-error=cancelled&provider=google")

    # Validate state nonce
    try:
        _consume_state(db, state, "google")
    except HTTPException:
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=google")

    try:
        redirect_uri = f"{BASE_URL}/api/auth/oauth/google/callback"

        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        id_token_raw = r.json()["id_token"]
        # Signature verification is unnecessary for server-side code exchange —
        # the token came directly from Google's token endpoint over HTTPS.
        claims = jose_jwt.decode(id_token_raw, options={"verify_signature": False})

        ip = request.client.host if request and request.client else None

    except Exception as exc:
        print(f"[oauth/google] network/parse error: {exc}", file=sys.stderr)
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=google")

    # upsert_oauth_user may raise HTTPException for unverified/missing email
    try:
        result = upsert_oauth_user(
            db,
            provider="google",
            oauth_id=claims["sub"],
            email=claims.get("email"),
            verified=bool(claims.get("email_verified")),
            display_name=claims.get("name"),
            ip=ip,
        )
    except HTTPException as exc:
        print(f"[oauth/google] upsert rejected: {exc.detail}", file=sys.stderr)
        return RedirectResponse(f"{BASE_URL}/#oauth-error=failed&provider=google")

    if result["status"] == "2fa_required":
        return RedirectResponse(f"{BASE_URL}/#oauth-2fa={result['partial_token']}")
    elif result["status"] == "ok":
        return RedirectResponse(f"{BASE_URL}/#token={result['token']}")
    else:
        return RedirectResponse(f"{BASE_URL}/#oauth-confirm={result['pending_token']}")


# ---------------------------------------------------------------------------
# Confirm-link endpoint
# ---------------------------------------------------------------------------

class ConfirmLinkPayload(BaseModel):
    pending_token: str
    password: str


@router.post("/auth/oauth/confirm-link")
def confirm_link(payload: ConfirmLinkPayload, db: Session = Depends(get_db), request: Request = None):
    """
    Complete the same-email account-link flow.

    Validates the pending-link token, checks the password, creates OAuthIdentity,
    and issues a JWT.
    """
    now = datetime.now(timezone.utc).isoformat()

    row = db.query(models.OAuthPendingLink).filter(
        models.OAuthPendingLink.state_token == payload.pending_token,
    ).first()

    if not row or row.expires_at <= now:
        raise HTTPException(
            status_code=400,
            detail="Link session expired. Please try signing in again.",
        )

    user = db.query(models.User).filter(models.User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Link session expired. Please try signing in again.")

    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect password.")

    # Create the durable identity link
    link_now = datetime.now(timezone.utc).isoformat()
    identity = models.OAuthIdentity(
        user_id=row.user_id,
        provider=row.provider,
        oauth_id=row.oauth_id,
        email=row.email,
        created_at=link_now,
    )
    db.add(identity)
    db.delete(row)
    db.commit()
    db.refresh(identity)

    log_event(
        EVT_OAUTH_LINK,
        actor_id=user.id,
        actor_email=user.email,
        description=f"{user.email} linked {row.provider} OAuth identity",
        target_type="oauth_identity",
        target_id=str(identity.id),
    )

    ip = request.client.host if request and request.client else None
    if user.totp_enabled:
        from ..totp_utils import create_partial_token
        return {"status": "2fa_required", "partial_token": create_partial_token(user.id)}

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "user": _user_dict(user),
    }
