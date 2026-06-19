"""
totp_utils.py — TOTP 2FA primitives for Phase 15.

Public API consumed by:
- backend/routers/totp.py (/auth/login/2fa endpoint)
- backend/routers/totp.py (/me/2fa/* enrollment/management endpoints, Plan 15-02)
- backend/tests/test_totp.py
"""
import base64
import hashlib
import io
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pyotp
import qrcode
from cryptography.fernet import Fernet
from fastapi import HTTPException
from jose import JWTError, jwt

from .auth_utils import SECRET_KEY, ALGORITHM, pwd_context

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SAFE_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/O/1/l

# In-memory rate-limit store keyed by user_id: deque of failure timestamps
_2fa_rate_store: dict = defaultdict(deque)


# ---------------------------------------------------------------------------
# Fernet encryption — TOTP secret at rest
# ---------------------------------------------------------------------------

def _fernet() -> Fernet:
    """Return a Fernet instance keyed from SECRET_KEY (SHA-256 derived, 256-bit)."""
    raw = hashlib.sha256(SECRET_KEY.encode()).digest()  # 32 bytes
    return Fernet(base64.urlsafe_b64encode(raw))


def encrypt_totp_secret(secret: str) -> str:
    """Encrypt a plaintext TOTP base32 secret for storage in users.totp_secret."""
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(enc: str) -> str:
    """Decrypt a previously encrypted TOTP secret."""
    return _fernet().decrypt(enc.encode()).decode()


# ---------------------------------------------------------------------------
# Partial token — scope=2fa_pending, 5-minute TTL
# ---------------------------------------------------------------------------

def create_partial_token(user_id: int) -> str:
    """Issue a short-lived JWT with scope=2fa_pending. NOT a full session token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode(
        {"sub": str(user_id), "scope": "2fa_pending", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_partial_token(token: str) -> int:
    """
    Validate a 2fa_pending partial token and return user_id.

    Raises HTTPException(401) for:
    - Invalid/expired JWT
    - Wrong scope (e.g. full session token submitted here)
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "2fa_pending":
            raise HTTPException(status_code=401, detail="Invalid token scope")
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# TOTP verification
# ---------------------------------------------------------------------------

def verify_totp_code(encrypted_secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against an encrypted secret. ±1 step tolerance."""
    secret = decrypt_totp_secret(encrypted_secret)
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ---------------------------------------------------------------------------
# TOTP setup (enrollment Step 1) — generates secret + QR data URI
# ---------------------------------------------------------------------------

def generate_totp_setup(user_email: str) -> dict:
    """
    Generate a fresh TOTP secret and return setup data for the enrollment dialog.

    Returns: {"secret": <base32 plaintext>, "qr_data_uri": "data:image/png;base64,..."}
    Note: secret is NOT encrypted here — it is passed back by the frontend in Step 2
    so we can verify the TOTP code before encrypting and persisting it.
    """
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=user_email, issuer_name="ThoroTest")

    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    return {
        "secret": secret,           # display as copyable fallback in UI
        "qr_data_uri": qr_data_uri, # embed in <img> tag with white background
    }


# ---------------------------------------------------------------------------
# Recovery codes — generation and verification
# ---------------------------------------------------------------------------

def generate_recovery_codes() -> list[tuple[str, str]]:
    """
    Generate 10 single-use recovery codes.

    Returns a list of (plaintext, sha256_crypt_hash) tuples.
    Store hashes in DB; display plaintexts once at enrollment.
    Format: 'xxxx-xxxx' (8 chars from _SAFE_CHARS, dash in middle)
    """
    codes = []
    for _ in range(10):
        half1 = "".join(secrets.choice(_SAFE_CHARS) for _ in range(4))
        half2 = "".join(secrets.choice(_SAFE_CHARS) for _ in range(4))
        plain = f"{half1}-{half2}"
        codes.append((plain, pwd_context.hash(plain)))
    return codes


def verify_recovery_code(plain: str, rows: list):
    """
    Find and return the first unused recovery code row that matches plain.

    Args:
        plain: The plaintext recovery code submitted by the user.
        rows: List of TotpRecoveryCode ORM rows (used=False filtered by caller).

    Returns: The matching row, or None if no match.
    """
    for row in rows:
        if not row.used and pwd_context.verify(plain, row.code_hash):
            return row
    return None


# ---------------------------------------------------------------------------
# Rate limiting — failed 2FA attempts
# ---------------------------------------------------------------------------

def check_2fa_rate(user_id: int, max_attempts: int = 5, window_sec: int = 30) -> tuple[bool, int]:
    """
    Check if the user is within the allowed attempt window.

    Only FAILED attempts are counted — the endpoint calls record_2fa_failure()
    on a wrong code. Successful verifications do not count against the limit.

    Returns: (allowed, retry_after_seconds)
      - allowed=True: request may proceed
      - allowed=False: rate limit exceeded; retry_after is seconds until oldest entry expires
    """
    now = time.time()
    dq = _2fa_rate_store[user_id]
    # Prune entries outside the window
    while dq and dq[0] < now - window_sec:
        dq.popleft()
    if len(dq) >= max_attempts:
        retry_after = int(window_sec - (now - dq[0])) + 1
        return False, retry_after
    return True, 0


def record_2fa_failure(user_id: int) -> None:
    """Record a failed 2FA attempt timestamp for rate-limit tracking."""
    _2fa_rate_store[user_id].append(time.time())
