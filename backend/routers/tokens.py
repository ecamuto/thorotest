import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import ApiTokenOut, ApiTokenCreate, ApiTokenCreated
from ..auth_utils import require_role, API_TOKEN_EXPIRE_DAYS, READ_SCOPE

router = APIRouter(tags=["tokens"])

# Any role that can act on data may mint a token for itself. Restricting minting
# to admins made every token in the system an admin token, which is the opposite
# of least privilege — a CI runner should carry the narrowest credential that
# does its job. Callers only ever see and revoke their own tokens; admins see all.
TOKEN_ROLES = require_role("admin", "manager", "tester", "viewer")

VALID_SCOPES = {READ_SCOPE, "write"}


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _visible_tokens(db: Session, user: models.User):
    q = db.query(models.ApiToken)
    if user.role != "admin":
        q = q.filter(models.ApiToken.user_id == user.id)
    return q


@router.get("/tokens", response_model=List[ApiTokenOut])
def list_tokens(db: Session = Depends(get_db), current_user: models.User = TOKEN_ROLES):
    return _visible_tokens(db, current_user).all()


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(payload: ApiTokenCreate, db: Session = Depends(get_db), current_user: models.User = TOKEN_ROLES):
    scope = (payload.scope or "write").strip().lower()
    if scope not in VALID_SCOPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scope. Must be one of: {sorted(VALID_SCOPES)}",
        )
    # A viewer cannot write through the UI, so it must not be able to mint a
    # token that writes either.
    if scope != READ_SCOPE and current_user.role == "viewer":
        raise HTTPException(status_code=403, detail="Your role can only create read-scoped tokens.")

    raw = "th_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    now = datetime.now(timezone.utc)
    expires_at = payload.expires_at or (now + timedelta(days=API_TOKEN_EXPIRE_DAYS)).isoformat()
    tok = models.ApiToken(
        name=payload.name,
        token_hash=_hash_token(raw),
        token_prefix=prefix,
        scope=scope,
        user_id=current_user.id,   # token authenticates as its creator
        created_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        expires_at=expires_at,
        # Captured so logout / password reset revokes this token with the
        # owner's sessions.
        token_version=int(current_user.token_version or 0),
    )
    db.add(tok)
    db.commit()
    db.refresh(tok)
    return ApiTokenCreated(
        id=tok.id,
        name=tok.name,
        token_prefix=tok.token_prefix,
        scope=tok.scope,
        created_at=tok.created_at,
        last_used_at=tok.last_used_at,
        expires_at=tok.expires_at,
        token=raw,
    )


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, db: Session = Depends(get_db), current_user: models.User = TOKEN_ROLES):
    tok = _visible_tokens(db, current_user).filter(models.ApiToken.id == token_id).first()
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    db.delete(tok)
    db.commit()
