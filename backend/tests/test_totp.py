"""
test_totp.py — pytest coverage for partial-token + 2FA login + recovery + rate limit,
               plus enrollment, disable, and regenerate endpoints (Plan 15-02).
"""
import re
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db
from backend import models
from backend.auth_utils import hash_password, create_access_token
from backend.totp_utils import encrypt_totp_secret, create_partial_token
import pyotp


# ---------------------------------------------------------------------------
# Helper — creates a User with totp_enabled=True and a known Fernet-encrypted secret
# ---------------------------------------------------------------------------

def _make_2fa_user(db, secret: str) -> models.User:
    """Create and commit a User with 2FA enabled using the provided base32 TOTP secret."""
    user = models.User(
        username="totp_user",
        email="totp@test.com",
        hashed_password=hash_password("pass123"),
        display_name="TOTP User",
        role="tester",
        totp_enabled=True,
        totp_secret=encrypt_totp_secret(secret),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Client factory helper
# ---------------------------------------------------------------------------

def _raw_client(db) -> TestClient:
    """TestClient without pre-set auth headers, using the in-memory DB."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_login_returns_partial_token(db):
    """2FA user: correct password → status=2fa_required + partial_token, NO access_token."""
    secret = pyotp.random_base32()
    _make_2fa_user(db, secret)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "2fa_required"
        assert "partial_token" in data
        assert "access_token" not in data
    finally:
        app.dependency_overrides.clear()


def test_2fa_login_valid_totp(db):
    """Submit partial_token + valid TOTP code → 200 + full access_token."""
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        # Step 1: password login → partial token
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        assert resp.status_code == 200
        partial_token = resp.json()["partial_token"]

        # Step 2: submit valid TOTP code
        code = pyotp.TOTP(secret).now()
        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": code})
        assert resp2.status_code == 200
        data = resp2.json()
        assert "access_token" in data
        assert data.get("token_type") == "bearer"
        assert "user" in data
    finally:
        app.dependency_overrides.clear()


def test_2fa_login_bad_totp(db):
    """Submit partial_token + wrong TOTP code → 400 Invalid code."""
    secret = pyotp.random_base32()
    _make_2fa_user(db, secret)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        partial_token = resp.json()["partial_token"]

        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": "000000"})
        assert resp2.status_code == 400
        assert "Invalid code" in resp2.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()


def test_2fa_recovery_code_login(db):
    """Submit partial_token + valid recovery code → 200 + full access_token."""
    from backend.totp_utils import generate_recovery_codes
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    # Insert known recovery codes
    code_pairs = generate_recovery_codes()
    now = datetime.now(timezone.utc).isoformat()
    for _, code_hash in code_pairs:
        db.add(models.TotpRecoveryCode(
            user_id=user.id,
            code_hash=code_hash,
            used=False,
            created_at=now,
        ))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        partial_token = resp.json()["partial_token"]

        # Use the first plaintext recovery code
        plain = code_pairs[0][0]
        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": plain})
        assert resp2.status_code == 200
        data = resp2.json()
        assert "access_token" in data
    finally:
        app.dependency_overrides.clear()


def test_recovery_code_single_use(db):
    """Recovery code is single-use: second attempt with the same code → 400."""
    from backend.totp_utils import generate_recovery_codes
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    code_pairs = generate_recovery_codes()
    now = datetime.now(timezone.utc).isoformat()
    for _, code_hash in code_pairs:
        db.add(models.TotpRecoveryCode(
            user_id=user.id,
            code_hash=code_hash,
            used=False,
            created_at=now,
        ))
    db.commit()
    plain = code_pairs[0][0]

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)

        # First use — should succeed
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        partial_token = resp.json()["partial_token"]
        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": plain})
        assert resp2.status_code == 200

        # Second use — must fail (need a new partial token since the old one is still valid)
        resp3 = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        partial_token2 = resp3.json()["partial_token"]
        resp4 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token2, "code": plain})
        assert resp4.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_2fa_rate_limit(db):
    """6 bad attempts in 30s window → 429 with retry_after."""
    from backend import totp_utils
    secret = pyotp.random_base32()
    _make_2fa_user(db, secret)

    # Reset rate limit store for this user to avoid cross-test contamination
    # We'll get the user_id after login
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        partial_token = resp.json()["partial_token"]

        # Clear any existing rate limit state for this test
        totp_utils._2fa_rate_store.clear()

        # Make 5 failed attempts (fills window)
        for _ in range(5):
            client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": "000000"})

        # 6th attempt should be rate-limited
        resp_limited = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": "000000"})
        assert resp_limited.status_code == 429
        detail = resp_limited.json().get("detail", "")
        assert "Too many attempts" in detail
    finally:
        app.dependency_overrides.clear()


def test_2fa_rejects_full_session_token(db):
    """A full session JWT submitted as partial_token must be rejected (401)."""
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    # Mint a full session token directly
    full_token = create_access_token(user.id)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        code = pyotp.TOTP(secret).now()
        resp = client.post("/api/auth/login/2fa", json={"partial_token": full_token, "code": code})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# Plan 15-02: Enrollment, disable, and regenerate tests
# ===========================================================================

def test_setup_returns_secret_and_qr(auth_client):
    """GET /me/2fa/setup returns a non-empty secret and a QR PNG data URI."""
    client = auth_client("tester")
    resp = client.get("/api/me/2fa/setup")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("secret"), "expected non-empty 'secret'"
    assert isinstance(data["secret"], str) and len(data["secret"]) > 0
    assert data.get("qr_data_uri", "").startswith("data:image/png;base64,"), (
        "expected qr_data_uri to start with data:image/png;base64,"
    )


def test_enable_returns_recovery_codes(auth_client, db):
    """
    GET setup → submit valid TOTP code → POST enable → 200, 10 recovery codes,
    user.totp_enabled True, 10 TotpRecoveryCode rows.
    """
    client = auth_client("tester")

    # Step 1: get setup data
    resp = client.get("/api/me/2fa/setup")
    assert resp.status_code == 200
    secret = resp.json()["secret"]

    # Step 2: compute live TOTP code and enable
    totp_code = pyotp.TOTP(secret).now()
    resp2 = client.post("/api/me/2fa/enable", json={
        "pending_secret": secret,
        "totp_code": totp_code,
    })
    assert resp2.status_code == 200
    data = resp2.json()
    codes = data.get("recovery_codes", [])

    assert len(codes) == 10, f"expected 10 recovery codes, got {len(codes)}"
    code_pattern = re.compile(r"^[a-z2-9]{4}-[a-z2-9]{4}$")
    for c in codes:
        assert code_pattern.match(c), f"code '{c}' does not match xxxx-xxxx format"

    # Verify DB state: user.totp_enabled=True, 10 recovery rows
    # The auth_client user was named "test_tester" in the conftest factory
    user = db.query(models.User).filter(models.User.username == "test_tester").first()
    assert user is not None
    assert user.totp_enabled is True
    assert db.query(models.TotpRecoveryCode).filter_by(user_id=user.id).count() == 10


def test_enable_rejects_bad_totp(auth_client, db):
    """POST /me/2fa/enable with a wrong TOTP code → 400; user remains not enrolled."""
    client = auth_client("tester")

    resp = client.get("/api/me/2fa/setup")
    assert resp.status_code == 200
    secret = resp.json()["secret"]

    resp2 = client.post("/api/me/2fa/enable", json={
        "pending_secret": secret,
        "totp_code": "000000",
    })
    assert resp2.status_code == 400

    user = db.query(models.User).filter(models.User.username == "test_tester").first()
    assert user is not None
    assert user.totp_enabled is False
    assert db.query(models.TotpRecoveryCode).filter_by(user_id=user.id).count() == 0


def _enroll_user(client, db):
    """
    Helper: enroll a user via the setup/enable flow and return (secret, recovery_codes).
    Caller must already have client authenticated with auth_client.
    """
    resp = client.get("/api/me/2fa/setup")
    assert resp.status_code == 200
    secret = resp.json()["secret"]

    totp_code = pyotp.TOTP(secret).now()
    resp2 = client.post("/api/me/2fa/enable", json={
        "pending_secret": secret,
        "totp_code": totp_code,
    })
    assert resp2.status_code == 200
    codes = resp2.json()["recovery_codes"]
    return secret, codes


def test_disable_2fa_valid_code(auth_client, db):
    """Enroll, then DELETE /me/2fa/disable with a live TOTP → clears secret, flag, codes."""
    client = auth_client("tester")
    secret, _ = _enroll_user(client, db)

    disable_code = pyotp.TOTP(secret).now()
    resp = client.request("DELETE", "/api/me/2fa/disable", json={"totp_code": disable_code})
    assert resp.status_code == 200

    # Verify DB state fully cleared
    user = db.query(models.User).filter(models.User.username == "test_tester").first()
    db.refresh(user)
    assert user.totp_secret is None
    assert user.totp_enabled is False
    assert db.query(models.TotpRecoveryCode).filter_by(user_id=user.id).count() == 0


def test_disable_2fa_wrong_code(auth_client, db):
    """DELETE /me/2fa/disable with wrong TOTP → 400; 2FA remains active."""
    client = auth_client("tester")
    _enroll_user(client, db)

    resp = client.request("DELETE", "/api/me/2fa/disable", json={"totp_code": "000000"})
    assert resp.status_code == 400

    user = db.query(models.User).filter(models.User.username == "test_tester").first()
    db.refresh(user)
    assert user.totp_enabled is True
    assert user.totp_secret is not None


def test_bad_totp_emits_2fa_fail_audit_row(db):
    """Bad TOTP code → 400 + exactly one AuditLog row with event_type=2fa_fail."""
    from backend import totp_utils
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    totp_utils._2fa_rate_store.clear()
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        assert resp.status_code == 200
        partial_token = resp.json()["partial_token"]

        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": "000000"})
        assert resp2.status_code == 400

        rows = db.query(models.AuditLog).filter_by(event_type="2fa_fail").all()
        assert len(rows) == 1
        assert rows[0].outcome == "fail"
        assert rows[0].actor_email == user.email
        assert "TOTP" in rows[0].description
    finally:
        app.dependency_overrides.clear()


def test_bad_recovery_code_emits_2fa_fail_audit_row(db):
    """Bad recovery code → 400 + exactly one AuditLog row with event_type=2fa_fail."""
    from backend.totp_utils import generate_recovery_codes
    from backend import totp_utils
    secret = pyotp.random_base32()
    user = _make_2fa_user(db, secret)

    # Insert known recovery codes
    code_pairs = generate_recovery_codes()
    now = datetime.now(timezone.utc).isoformat()
    for _, code_hash in code_pairs:
        db.add(models.TotpRecoveryCode(
            user_id=user.id,
            code_hash=code_hash,
            used=False,
            created_at=now,
        ))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    totp_utils._2fa_rate_store.clear()
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        assert resp.status_code == 200
        partial_token = resp.json()["partial_token"]

        # Submit a wrong recovery code in valid 9-char xxxx-xxxx format
        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": "zzzz-zzzz"})
        assert resp2.status_code == 400

        rows = db.query(models.AuditLog).filter_by(event_type="2fa_fail").all()
        assert len(rows) == 1
        assert rows[0].outcome == "fail"
        assert rows[0].actor_email == user.email
        assert "recovery" in rows[0].description
    finally:
        app.dependency_overrides.clear()


def test_successful_2fa_login_no_2fa_fail_row(db):
    """Successful 2FA login emits NO 2fa_fail AuditLog row (no false positives)."""
    from backend import totp_utils
    secret = pyotp.random_base32()
    _make_2fa_user(db, secret)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    totp_utils._2fa_rate_store.clear()
    try:
        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"email": "totp@test.com", "password": "pass123"})
        assert resp.status_code == 200
        partial_token = resp.json()["partial_token"]

        # Submit a valid TOTP code
        code = pyotp.TOTP(secret).now()
        resp2 = client.post("/api/auth/login/2fa", json={"partial_token": partial_token, "code": code})
        assert resp2.status_code == 200

        count = db.query(models.AuditLog).filter_by(event_type="2fa_fail").count()
        assert count == 0, f"expected 0 2fa_fail rows on successful login, got {count}"
    finally:
        app.dependency_overrides.clear()


def test_regenerate_invalidates_old(auth_client, db):
    """
    Enroll, capture 10 codes, regenerate with valid TOTP → 10 NEW codes returned;
    an old plaintext code is rejected at /auth/login/2fa (invalidated by deletion).
    """
    client = auth_client("tester")
    secret, old_codes = _enroll_user(client, db)

    # Regenerate with a fresh TOTP code
    regen_code = pyotp.TOTP(secret).now()
    resp = client.post("/api/me/2fa/recovery-codes/regenerate", json={"totp_code": regen_code})
    assert resp.status_code == 200
    new_codes = resp.json().get("recovery_codes", [])

    assert len(new_codes) == 10, f"expected 10 new codes, got {len(new_codes)}"

    # Old codes should all be gone from DB (deleted atomically)
    user = db.query(models.User).filter(models.User.username == "test_tester").first()
    remaining_count = db.query(models.TotpRecoveryCode).filter_by(
        user_id=user.id, used=False
    ).count()
    assert remaining_count == 10, f"expected 10 fresh codes in DB, got {remaining_count}"

    # Verify an old code is rejected at /auth/login/2fa
    old_plain = old_codes[0]
    # Clear rate-limit state so prior test failures don't trigger 429 here
    from backend import totp_utils
    totp_utils._2fa_rate_store.clear()

    # Create a valid partial token for the enrolled user
    partial_token = create_partial_token(user.id)
    resp2 = client.post("/api/auth/login/2fa", json={
        "partial_token": partial_token,
        "code": old_plain,
    })
    assert resp2.status_code == 400, (
        f"expected 400 for invalidated recovery code, got {resp2.status_code}"
    )
