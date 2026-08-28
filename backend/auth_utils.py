import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from jwt import PyJWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from .db import get_db
from . import models

logger = logging.getLogger("thorotest.auth")

ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7
WS_TICKET_EXPIRE_SECONDS = 60

# Historic placeholder that shipped in .env.example. Still rejected by name so an
# existing .env carried forward from an older checkout fails loudly rather than
# silently signing tokens with a key published in the repo.
_DEFAULT_SECRET = "thorotest-dev-secret-change-in-production"

# The JWT signing key also derives the Fernet key that encrypts TOTP secrets at
# rest, so a known key means forgeable admin sessions AND readable 2FA secrets.
# This is enforced in EVERY environment, not just production: the failure mode is
# silent, and the deployment most likely to hit it (docker-compose with a copied
# .env.example) is exactly the one that never sets ENVIRONMENT.
_ALLOW_INSECURE = os.getenv("ALLOW_INSECURE_SECRET_KEY", "").strip().lower() in ("1", "true", "yes")
_MIN_SECRET_LENGTH = 32

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

if not _ALLOW_INSECURE:
    _problem = None
    if not SECRET_KEY:
        _problem = "SECRET_KEY is not set"
    elif SECRET_KEY == _DEFAULT_SECRET:
        _problem = "SECRET_KEY is the placeholder that ships in .env.example"
    elif len(SECRET_KEY) < _MIN_SECRET_LENGTH:
        _problem = f"SECRET_KEY is shorter than {_MIN_SECRET_LENGTH} characters"
    if _problem:
        raise RuntimeError(
            f"{_problem}. It signs session tokens and encrypts TOTP secrets, so a "
            "shared or guessable value lets anyone forge an admin session. Generate one:\n"
            '  python3 -c "import secrets; print(secrets.token_hex(32))"\n'
            "and set SECRET_KEY in the environment or .env before starting. "
            "For a throwaway local run only, set ALLOW_INSECURE_SECRET_KEY=1."
        )
elif not SECRET_KEY:
    # Explicitly opted out of the check and supplied nothing — use the historic
    # placeholder so local dev still boots, and say so on every start.
    SECRET_KEY = _DEFAULT_SECRET

if _ALLOW_INSECURE:
    logger.warning(
        "ALLOW_INSECURE_SECRET_KEY is set — the JWT signing key is not being "
        "validated. Never use this outside a throwaway local run."
    )

# argon2id is the primary scheme. sha256_crypt stays for verifying (and silently
# upgrading) hashes created before the migration. deprecated="auto" marks any
# non-argon2 hash as needing a rehash on next successful login.
pwd_context = CryptContext(schemes=["argon2", "sha256_crypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128

# Very common passwords long enough to pass the length check. Compared
# lowercase-exact. A breached-password service (HIBP) is the roadmap upgrade;
# this list only catches the worst offenders without a network dependency.
_COMMON_PASSWORDS = {
    "password1234", "password12345", "password123456",
    "123456789012", "1234567890123", "12345678901234",
    "qwertyuiop12", "qwertyuiopas", "qwerty123456",
    "adminadmin123", "administrator", "letmeinletmein",
    "welcome12345", "changeme12345", "iloveyou12345",
    "thorotest1234",
}


def validate_password(password: str, *, email: str | None = None, username: str | None = None) -> None:
    """Enforce the password policy; raise HTTPException(422) on violation.

    NIST-style: length + blocklist, no composition rules. Also rejects
    passwords built on the account's own identifiers.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {PASSWORD_MIN_LENGTH} characters",
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at most {PASSWORD_MAX_LENGTH} characters",
        )
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(lowered)) == 1:
        raise HTTPException(status_code=422, detail="Password is too common")
    for ident in (username, email.split("@", 1)[0] if email else None):
        if ident and len(ident) >= 4 and ident.lower() in lowered:
            raise HTTPException(
                status_code=422,
                detail="Password must not contain your username or email",
            )


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
    payload = {
        "sub": str(user_id), "scope": "session", "exp": expire,
        "tv": int(token_version or 0),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_websocket_ticket(user_id: int, token_version: int = 0) -> str:
    """Issue a narrowly scoped, short-lived credential for a WS handshake.

    Browsers cannot attach an Authorization header to WebSocket handshakes. A
    ticket may therefore appear in a query string, but unlike the seven-day
    session JWT it expires in one minute and cannot authenticate REST/GraphQL.
    """
    expire = datetime.now(timezone.utc) + timedelta(seconds=WS_TICKET_EXPIRE_SECONDS)
    payload = {
        "sub": str(user_id), "scope": "websocket", "exp": expire,
        "tv": int(token_version or 0),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# A read-scoped token may only issue safe requests. Enforcing by HTTP method
# covers every route uniformly instead of relying on 130 handlers to opt in.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
READ_SCOPE = "read"

# Default lifetime for a newly minted API token. Long enough for a CI runner not
# to churn, short enough that a leaked token stops working on its own.
API_TOKEN_EXPIRE_DAYS = int(os.getenv("API_TOKEN_EXPIRE_DAYS", "90"))


def _user_from_api_token(raw: str, db: Session, method: str) -> Optional[models.User]:
    """Resolve a `th_`-prefixed API token to its owning user, or None.

    The token authenticates as that user (inherits their role) and is rejected
    when expired, when its scope forbids the request's method, or when the
    owner's token_version has moved past the value captured at mint time
    (logout / "log out everywhere" / password reset). last_used_at is stamped.
    """
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    tok = db.query(models.ApiToken).filter(models.ApiToken.token_hash == token_hash).first()
    if not tok or not tok.user_id:
        return None

    now = datetime.now(timezone.utc)
    if tok.expires_at and tok.expires_at < now.isoformat():
        return None

    user = db.query(models.User).filter(models.User.id == tok.user_id).first()
    if user is None:
        return None
    if int(tok.token_version or 0) != int(user.token_version or 0):
        return None

    # Scope is a real restriction, not a label: a read token cannot write even
    # though it authenticates as a user whose role permits writes.
    if (tok.scope or "").strip().lower() == READ_SCOPE and method.upper() not in _SAFE_METHODS:
        raise HTTPException(
            status_code=403,
            detail="This API token is read-only.",
        )

    tok.last_used_at = now.strftime("%Y-%m-%d %H:%M UTC")
    db.commit()
    return user


def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not credentials:
        return None
    # Long-lived API tokens (th_…) for CI / scripts, resolved before JWT.
    if credentials.credentials.startswith("th_"):
        return _user_from_api_token(credentials.credentials, db, request.method)
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        # Legacy session JWTs had no scope. Continue accepting those until their
        # natural seven-day expiry, but never promote 2FA-pending or WS tickets.
        if payload.get("scope") not in (None, "session"):
            return None
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
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


def user_from_bearer_token(token: str, db: Session) -> Optional[models.User]:
    """Resolve a raw bearer token string to a User, or None.

    The transport-independent core of get_optional_user for the GraphQL context
    builder. Applies the same scope and token_version checks as REST so GraphQL
    cannot accept a partial or revoked session.

    API tokens are deliberately not accepted here; REST resolves those through
    the database-backed API-token path instead.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") not in (None, "session"):
            return None
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        return None
    if int(payload.get("tv", 0)) != int(user.token_version or 0):
        return None
    return user


def user_from_websocket_ticket(ticket: str, db: Session) -> Optional[models.User]:
    """Resolve only a scope=websocket ticket; session/API/2FA tokens fail."""
    if not ticket:
        return None
    try:
        payload = jwt.decode(ticket, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "websocket":
            return None
        user_id = int(payload.get("sub"))
    except (PyJWTError, ValueError, TypeError):
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        return None
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
