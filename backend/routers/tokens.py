import secrets
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import ApiTokenOut, ApiTokenCreate, ApiTokenCreated
from ..auth_utils import require_role

router = APIRouter(tags=["tokens"])

# API tokens grant programmatic access — restrict all management to admins.
ADMIN_ONLY = require_role("admin")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("/tokens", response_model=List[ApiTokenOut])
def list_tokens(db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    return db.query(models.ApiToken).all()


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(payload: ApiTokenCreate, db: Session = Depends(get_db), current_user: models.User = ADMIN_ONLY):
    raw = "th_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    token_hash = _hash_token(raw)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tok = models.ApiToken(
        name=payload.name,
        token_hash=token_hash,
        token_prefix=prefix,
        scope=payload.scope,
        user_id=current_user.id,   # token authenticates as its creator
        created_at=now,
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
        token=raw,
    )


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    tok = db.query(models.ApiToken).filter(models.ApiToken.id == token_id).first()
    if not tok:
        raise HTTPException(status_code=404, detail="Token not found")
    db.delete(tok)
    db.commit()
