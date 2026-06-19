import time
import threading
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..schemas import UserCreate, UserLogin, UserOut, UserListItem, UserUpdate, PasswordChange
from ..auth_utils import hash_password, verify_password, create_access_token, get_current_user
from ..totp_utils import create_partial_token
from ..audit_utils import (
    log_event,
    EVT_LOGIN_SUCCESS, EVT_LOGIN_FAIL, EVT_LOGOUT,
    EVT_PASSWORD_CHANGE, EVT_PASSWORD_CHANGE_FAIL,
)

router = APIRouter(tags=["auth"])

# ── Login throttling (brute-force protection) ────────────────────────────────
# Counts only FAILED attempts per (ip, email); a successful login clears the
# counter. Successful logins are never throttled, so legitimate traffic and
# automated test logins are unaffected.
_LOGIN_MAX_FAILURES = 10
_LOGIN_WINDOW_SECONDS = 300
_login_failures: dict = defaultdict(deque)
_login_lock = threading.Lock()


def _login_key(ip, email):
    return f"{ip}|{(email or '').lower()}"


def _check_login_rate(key: str) -> None:
    now = time.time()
    with _login_lock:
        dq = _login_failures[key]
        while dq and dq[0] < now - _LOGIN_WINDOW_SECONDS:
            dq.popleft()
        if len(dq) >= _LOGIN_MAX_FAILURES:
            raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later.")


def _record_login_failure(key: str) -> None:
    with _login_lock:
        _login_failures[key].append(time.time())


def _clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)


@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if len(payload.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username taken")
    user = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name or payload.username,
        role="tester",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/auth/login")
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    ip = request.client.host if request.client else None
    rate_key = _login_key(ip, payload.email)
    _check_login_rate(rate_key)
    if not user or not verify_password(payload.password, user.hashed_password):
        _record_login_failure(rate_key)
        log_event(
            EVT_LOGIN_FAIL,
            actor_email=payload.email,
            description=f"{payload.email} failed to log in",
            outcome="fail",
            ip_address=ip,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_login_failures(rate_key)
    log_event(
        EVT_LOGIN_SUCCESS,
        actor_id=user.id,
        actor_email=user.email,
        description=f"{user.email} logged in successfully",
        ip_address=ip,
    )
    # 2FA chokepoint: if enabled, issue a partial token instead of a full JWT
    if user.totp_enabled:
        partial = create_partial_token(user.id)
        return {"status": "2fa_required", "partial_token": partial}

    token = create_access_token(user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "language": user.language or "en",
        },
    }


@router.post("/auth/logout", status_code=204)
def logout(request: Request, current_user: models.User = Depends(get_current_user)):
    ip = request.client.host if request.client else None
    log_event(
        EVT_LOGOUT,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} logged out",
        ip_address=ip,
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.put("/me", response_model=UserOut)
def update_me(payload: UserUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if payload.email and payload.email != current_user.email:
        if db.query(models.User).filter(models.User.email == payload.email, models.User.id != current_user.id).first():
            raise HTTPException(status_code=409, detail="Email already in use")
        current_user.email = payload.email
    if payload.display_name is not None:
        current_user.display_name = payload.display_name
    if payload.language is not None:
        current_user.language = payload.language
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/users", response_model=list[UserListItem])
def list_users(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # Returns a minimal directory (no email/PII) — used by assignment dropdowns
    # and @-mentions, so it must stay available to all authenticated roles.
    return db.query(models.User).order_by(models.User.display_name).all()


@router.put("/me/password", status_code=204)
def change_password(
    request: Request,
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ip = request.client.host if request.client else None
    if not verify_password(payload.current_password, current_user.hashed_password):
        log_event(
            EVT_PASSWORD_CHANGE_FAIL,
            actor_id=current_user.id,
            actor_email=current_user.email,
            description=f"{current_user.email} failed to change password (wrong current password)",
            outcome="fail",
            ip_address=ip,
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=422, detail="New password must be at least 6 characters")
    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_event(
        EVT_PASSWORD_CHANGE,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} changed their password",
        ip_address=ip,
    )
