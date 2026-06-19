"""
test_oauth.py — GitHub OAuth + account-linking test coverage.

Covers upsert_oauth_user() directly (avoids mocking the GitHub HTTP layer)
and the confirm-link endpoint via TestClient.
"""
import pytest
from fastapi import HTTPException

from backend import models
from backend.auth_utils import hash_password
from backend.routers.oauth import upsert_oauth_user


# ---------------------------------------------------------------------------
# Helper: create a seeded pending link row for confirm-link tests
# ---------------------------------------------------------------------------

def _seed_pending_link(db, state_token: str, user: models.User, provider: str, oauth_id: str, expires_minutes: int = 20):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    row = models.OAuthPendingLink(
        state_token=state_token,
        provider=provider,
        oauth_id=oauth_id,
        email=user.email,
        display_name=user.display_name,
        user_id=user.id,
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=expires_minutes)).isoformat(),
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# upsert_oauth_user() tests
# ---------------------------------------------------------------------------

def test_new_user_provisioned_viewer(db):
    """A completely new OAuth user gets a viewer-role account and an OAuthIdentity."""
    result = upsert_oauth_user(db, "github", "12345", "new@x.com", True, "New Person", None)

    assert result["status"] == "ok"
    assert result["token"]

    user = db.query(models.User).filter(models.User.email == "new@x.com").first()
    assert user is not None
    assert user.role == "viewer"
    assert user.hashed_password == "!"

    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == "github",
        models.OAuthIdentity.oauth_id == "12345",
    ).first()
    assert identity is not None
    assert identity.user_id == user.id


def test_returning_identity_logs_into_bound_account(db):
    """A returning user with an existing OAuthIdentity logs into the bound account."""
    # Pre-create the user and linked identity
    existing_user = models.User(
        username="bound_user",
        email="bound@x.com",
        hashed_password="!",
        display_name="Bound User",
        role="tester",
    )
    db.add(existing_user)
    db.flush()

    identity = models.OAuthIdentity(
        user_id=existing_user.id,
        provider="github",
        oauth_id="999",
        email="bound@x.com",
        created_at="2026-01-01T00:00:00Z",
    )
    db.add(identity)
    db.commit()

    user_count_before = db.query(models.User).count()

    result = upsert_oauth_user(db, "github", "999", "whatever@x.com", True, "Anything", None)

    assert result["status"] == "ok"
    assert result["user"]["id"] == existing_user.id
    # No new user created
    assert db.query(models.User).count() == user_count_before


def test_email_match_returns_link_required(db):
    """When OAuth email matches an existing local account, link_required is returned."""
    local_user = models.User(
        username="local_dup",
        email="dup@x.com",
        hashed_password=hash_password("localpass"),
        display_name="Local User",
        role="tester",
    )
    db.add(local_user)
    db.commit()

    user_count_before = db.query(models.User).count()

    result = upsert_oauth_user(db, "github", "777", "dup@x.com", True, "Some Person", None)

    assert result["status"] == "link_required"
    assert result["pending_token"]

    # No new user created
    assert db.query(models.User).count() == user_count_before
    # No OAuthIdentity created yet
    assert db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.oauth_id == "777"
    ).first() is None
    # A pending link row exists
    pending = db.query(models.OAuthPendingLink).filter(
        models.OAuthPendingLink.state_token == result["pending_token"]
    ).first()
    assert pending is not None
    assert pending.provider == "github"
    assert pending.oauth_id == "777"


def test_unverified_email_blocks(db):
    """Unverified provider email raises HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        upsert_oauth_user(db, "github", "888", "unverified@x.com", False, "Someone", None)
    assert exc_info.value.status_code == 400


def test_no_email_blocks(db):
    """Missing provider email raises HTTP 400."""
    with pytest.raises(HTTPException) as exc_info:
        upsert_oauth_user(db, "github", "889", None, True, "Someone", None)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Confirm-link endpoint tests
# ---------------------------------------------------------------------------

def test_confirm_link_wrong_password_401(client, db):
    """Wrong password returns 401 and does not create an OAuthIdentity."""
    user = models.User(
        username="link_test_user",
        email="linktest@x.com",
        hashed_password=hash_password("right"),
        display_name="Link Test",
        role="tester",
    )
    db.add(user)
    db.flush()

    _seed_pending_link(db, "pt1", user, "github", "555")

    resp = client.post("/api/auth/oauth/confirm-link", json={
        "pending_token": "pt1",
        "password": "wrong",
    })
    assert resp.status_code == 401

    # No identity created
    assert db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.oauth_id == "555"
    ).first() is None


def test_confirm_link_correct_password_links_and_issues_jwt(client, db):
    """Correct password creates OAuthIdentity, deletes pending link, and returns JWT."""
    user = models.User(
        username="link_test_user2",
        email="linktest2@x.com",
        hashed_password=hash_password("right"),
        display_name="Link Test 2",
        role="tester",
    )
    db.add(user)
    db.flush()

    _seed_pending_link(db, "pt2", user, "github", "555")

    resp = client.post("/api/auth/oauth/confirm-link", json={
        "pending_token": "pt2",
        "password": "right",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["id"] == user.id

    # OAuthIdentity created
    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == "github",
        models.OAuthIdentity.oauth_id == "555",
    ).first()
    assert identity is not None
    assert identity.user_id == user.id

    # Pending link row deleted
    assert db.query(models.OAuthPendingLink).filter(
        models.OAuthPendingLink.state_token == "pt2"
    ).first() is None


# ---------------------------------------------------------------------------
# 2FA gating tests
# ---------------------------------------------------------------------------

def test_returning_identity_totp_enabled_returns_2fa_required(db):
    """A returning OAuth user with totp_enabled=True receives 2fa_required, not a full JWT."""
    user = models.User(
        username="totp_user",
        email="totp@x.com",
        hashed_password="!",
        display_name="TOTP User",
        role="tester",
        totp_enabled=True,
        totp_secret="DUMMYSECRET",
    )
    db.add(user)
    db.flush()

    identity = models.OAuthIdentity(
        user_id=user.id,
        provider="github",
        oauth_id="totp-gh-1",
        email="totp@x.com",
        created_at="2026-01-01T00:00:00Z",
    )
    db.add(identity)
    db.commit()

    result = upsert_oauth_user(db, "github", "totp-gh-1", "totp@x.com", True, "TOTP User", "1.2.3.4")

    assert result["status"] == "2fa_required"
    assert "partial_token" in result
    assert "token" not in result


def test_returning_identity_non2fa_still_ok(db):
    """A returning OAuth user with totp_enabled=False still receives a full session (regression guard)."""
    user = models.User(
        username="non2fa_user",
        email="non2fa@x.com",
        hashed_password="!",
        display_name="Non 2FA User",
        role="tester",
        totp_enabled=False,
    )
    db.add(user)
    db.flush()

    identity = models.OAuthIdentity(
        user_id=user.id,
        provider="github",
        oauth_id="non2fa-gh-1",
        email="non2fa@x.com",
        created_at="2026-01-01T00:00:00Z",
    )
    db.add(identity)
    db.commit()

    result = upsert_oauth_user(db, "github", "non2fa-gh-1", "non2fa@x.com", True, "Non 2FA User", "1.2.3.4")

    assert result["status"] == "ok"
    assert "token" in result


def test_confirm_link_totp_enabled_returns_2fa_required(client, db):
    """confirm_link with totp_enabled user returns 2fa_required, link committed, no access_token."""
    user = models.User(
        username="totp_link_user",
        email="totplink@x.com",
        hashed_password=hash_password("right"),
        display_name="TOTP Link User",
        role="tester",
        totp_enabled=True,
        totp_secret="DUMMYSECRET2",
    )
    db.add(user)
    db.flush()

    _seed_pending_link(db, "pt_totp", user, "github", "totp-555")

    resp = client.post("/api/auth/oauth/confirm-link", json={
        "pending_token": "pt_totp",
        "password": "right",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "2fa_required"
    assert "partial_token" in data
    assert "access_token" not in data

    # OAuthIdentity WAS created — link committed before the 2FA gate
    identity = db.query(models.OAuthIdentity).filter(
        models.OAuthIdentity.provider == "github",
        models.OAuthIdentity.oauth_id == "totp-555",
    ).first()
    assert identity is not None
    assert identity.user_id == user.id


def test_confirm_link_expired_400(client, db):
    """Expired pending-link token returns 400."""
    user = models.User(
        username="link_test_user3",
        email="linktest3@x.com",
        hashed_password=hash_password("right"),
        display_name="Link Test 3",
        role="tester",
    )
    db.add(user)
    db.flush()

    # Seed with negative expiry (already expired)
    _seed_pending_link(db, "expired_pt", user, "github", "556", expires_minutes=-30)

    resp = client.post("/api/auth/oauth/confirm-link", json={
        "pending_token": "expired_pt",
        "password": "right",
    })
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()
