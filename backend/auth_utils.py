import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_db
from . import models

logger = logging.getLogger("thorotest.auth")

_DEFAULT_SECRET = "thorotest-dev-secret-change-in-production"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

# Refuse to boot with the placeholder JWT key in production; warn loudly otherwise.
if SECRET_KEY == _DEFAULT_SECRET:
    _env = os.getenv("ENVIRONMENT", os.getenv("ENV", "")).strip().lower()
    if _env in ("production", "prod"):
        raise RuntimeError(
            "SECRET_KEY is the built-in dev default in a production environment. "
            "Generate one: python3 -c \"import secrets; print(secrets.token_hex(32))\" "
            "and set SECRET_KEY in the environment / .env before starting."
        )
    logger.warning(
        "SECRET_KEY is the built-in dev default — INSECURE. "
        "Set a random SECRET_KEY before any non-local deployment."
    )

# argon2id is the primary scheme. sha256_crypt stays for verifying (and silently
# upgrading) hashes created before the migration. deprecated="auto" marks any
# non-argon2 hash as needing a rehash on next successful login.
pwd_context = CryptContext(schemes=["argon2", "sha256_crypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def verify_and_update(plain: str, hashed: str) -> Tuple[bool, Optional[str]]:
    """Verify a password and return (ok, new_hash).

    new_hash is a freshly computed argon2 hash when the stored hash uses a
    deprecated scheme (legacy sha256_crypt) — the caller should persist it.
    new_hash is None when verification fails or no upgrade is needed.
    """
    return pwd_context.verify_and_update(plain, hashed)


def create_access_token(user_id: int, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire, "tv": int(token_version or 0)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _user_from_api_token(raw: str, db: Session) -> Optional[models.User]:
    """Resolve a `th_`-prefixed API token to its owning user, or None. The token
    authenticates as that user (inherits their role); last_used_at is stamped."""
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    tok = db.query(models.ApiToken).filter(models.ApiToken.token_hash == token_hash).first()
    if not tok or not tok.user_id:
        return None
    user = db.query(models.User).filter(models.User.id == tok.user_id).first()
    if user is None:
        return None
    tok.last_used_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    db.commit()
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not credentials:
        return None
    # Long-lived API tokens (th_…) for CI / scripts, resolved before JWT.
    if credentials.credentials.startswith("th_"):
        return _user_from_api_token(credentials.credentials, db)
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        return None
    # Token revocation: a token is valid only while its embedded version matches
    # the user's current token_version. logout / "log out everywhere" bumps the
    # user's version, instantly invalidating all previously issued tokens.
    if int(payload.get("tv", 0)) != int(user.token_version or 0):
        return None
    return user


def get_current_user(
    user: Optional[models.User] = Depends(get_optional_user),
) -> models.User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_role(*allowed_roles: str):
    """Factory: returns a FastAPI Depends() that enforces role membership.

    Usage:
        ADMIN_ONLY = require_role("admin")
        WRITE_ROLES = require_role("admin", "manager", "tester")

    Raises HTTP 403 if caller's role is not in allowed_roles.
    Role is always read from DB (via get_current_user) — never from JWT payload.
    """
    def _check(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return Depends(_check)
