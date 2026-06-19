"""
test_oauth_google.py — Google OAuth provisioning + link-required coverage.

Tests the Google OAuth branch by calling upsert_oauth_user() with
provider="google" (proves Google reuses the same provisioning/linking path),
plus one callback-level test that mocks the httpx exchange + jose decode
to verify the sub claim becomes oauth_id.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import models
from backend.auth_utils import hash_password
from backend.routers.oauth import upsert_oauth_user


# ---------------------------------------------------------------------------
# upsert_oauth_user() — Google provider tests
# ---------------------------------------------------------------------------

def test_google_new_user_provisioned(db):
    """A new Google OAuth user gets a viewer-role account and OAuthIdentity with sub as oauth_id."""
    result = upsert_oauth_user(db, "google", "gsub-1", "g@x.com", True, "G User", None)

    assert result["status"] == "ok"
    assert result["token"]

    user = db.query(models.User).filter(models.User.email == "g@x.com").first()
    assert user is not None
    assert user.role == "viewer"
    assert user.hashed_password == "!"

    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == "google",
        models.OAuthIdentity.oauth_id == "gsub-1",
    ).first()
    assert identity is not None
    assert identity.user_id == user.id


def test_google_uses_sub_as_oauth_id(db):
    """OAuthIdentity created for Google user uses the sub claim (not email) as oauth_id."""
    upsert_oauth_user(db, "google", "gsub-1", "g@x.com", True, "G User", None)

    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == "google",
    ).first()
    assert identity is not None
    assert identity.oauth_id == "gsub-1"


def test_google_email_match_link_required(db):
    """Google email matching an existing local account returns link_required, no auto-link."""
    # Pre-create a local user with the same email
    local_user = models.User(
        username="local_dup_google",
        email="dup@x.com",
        hashed_password=hash_password("localpass"),
        display_name="Local User",
        role="tester",
    )
    db.add(local_user)
    db.commit()

    user_count_before = db.query(models.User).count()

    result = upsert_oauth_user(db, "google", "gsub-2", "dup@x.com", True, "G Person", None)

    assert result["status"] == "link_required"
    assert result["pending_token"]

    # No new user created
    assert db.query(models.User).count() == user_count_before

    # No OAuthIdentity created yet
    assert db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.oauth_id == "gsub-2"
    ).first() is None

    # An OAuthPendingLink row with provider="google" exists
    pending = db.query(models.OAuthPendingLink).filter(
        models.OAuthPendingLink.state_token == result["pending_token"]
    ).first()
    assert pending is not None
    assert pending.provider == "google"
    assert pending.oauth_id == "gsub-2"


def test_google_returning_identity_totp_enabled_returns_2fa_required(db):
    """A returning Google OAuth user with totp_enabled=True receives 2fa_required, not a full JWT."""
    user = models.User(
        username="g_totp_user",
        email="gtotp@x.com",
        hashed_password="!",
        display_name="Google TOTP User",
        role="tester",
        totp_enabled=True,
        totp_secret="DUMMYSECRETG",
    )
    db.add(user)
    db.flush()

    identity = models.OAuthIdentity(
        user_id=user.id,
        provider="google",
        oauth_id="gsub-totp-1",
        email="gtotp@x.com",
        created_at="2026-01-01T00:00:00Z",
    )
    db.add(identity)
    db.commit()

    result = upsert_oauth_user(db, "google", "gsub-totp-1", "gtotp@x.com", True, "Google TOTP User", "1.2.3.4")

    assert result["status"] == "2fa_required"
    assert "partial_token" in result
    assert "token" not in result


def test_google_unverified_blocked(db):
    """Unverified Google email raises HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        upsert_oauth_user(db, "google", "gsub-3", "unverified@x.com", False, "Someone", None)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Callback-level test — mocks httpx + jose to verify sub->oauth_id mapping
# ---------------------------------------------------------------------------

def test_google_callback_maps_sub_to_oauth_id(db):
    """
    Callback-level: mocked httpx exchange + jose decode confirms that
    claims['sub'] becomes the OAuthIdentity.oauth_id.
    """
    from backend.main import app
    from backend.db import get_db

    # Pre-insert a valid OAuthState for the test
    now = datetime.now(timezone.utc)
    db.add(models.OAuthState(
        state_token="st1",
        provider="google",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
    ))
    db.commit()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Mock the httpx AsyncClient to return a fake id_token response
        fake_response = MagicMock()
        fake_response.json.return_value = {"id_token": "fake.id.token"}

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_instance.post = AsyncMock(return_value=fake_response)

        # Mock jose_jwt.decode to return test claims
        fake_claims = {
            "sub": "gsub-9",
            "email": "cb@x.com",
            "email_verified": True,
            "name": "CB",
        }

        with patch("backend.routers.oauth.httpx.AsyncClient", return_value=mock_client_instance), \
             patch("backend.routers.oauth.jose_jwt.decode", return_value=fake_claims):

            with TestClient(app, follow_redirects=False) as tc:
                resp = tc.get("/api/auth/oauth/google/callback?code=abc&state=st1")

        # Should redirect with token fragment
        assert resp.status_code in (302, 307)
        assert "#token=" in resp.headers["location"]

        # OAuthIdentity created with google provider and gsub-9 as oauth_id
        identity = db.query(models.OAuthIdentity).filter(
            models.OAuthIdentity.provider == "google",
            models.OAuthIdentity.oauth_id == "gsub-9",
        ).first()
        assert identity is not None

    finally:
        app.dependency_overrides.clear()
