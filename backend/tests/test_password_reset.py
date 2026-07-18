"""Password reset flow: forgot-password request + token-based reset."""
import hashlib
from datetime import datetime, timedelta, timezone

from backend import models


def _reset_token_for(db, client, email="admin@test.com"):
    """Request a reset and return the raw token by intercepting the email."""
    sent = {}

    def fake_send(to, subject, body):
        sent["to"] = to
        sent["body"] = body
        return True

    import backend.routers.auth as auth_mod
    orig = auth_mod.send_email
    auth_mod.send_email = fake_send
    try:
        r = client.post("/api/auth/forgot-password", json={"email": email})
        assert r.status_code == 202
    finally:
        auth_mod.send_email = orig
    assert sent, "no email sent"
    # link format: {base}/#/reset-password/{token}
    token = sent["body"].split("/#/reset-password/")[1].split()[0]
    return token


class TestForgotPassword:
    def test_unknown_email_same_response_no_email(self, client, db):
        r = client.post("/api/auth/forgot-password", json={"email": "nobody@test.com"})
        assert r.status_code == 202
        assert "reset link" in r.json()["detail"]
        assert db.query(models.PasswordResetToken).count() == 0

    def test_known_email_creates_token_and_sends_link(self, client, db):
        token = _reset_token_for(db, client)
        assert len(token) > 20
        row = db.query(models.PasswordResetToken).one()
        assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert row.used is False


class TestResetPassword:
    def test_happy_path_changes_password_and_revokes_sessions(self, client, db):
        user = db.query(models.User).filter(models.User.email == "admin@test.com").first()
        old_tv = user.token_version or 0
        token = _reset_token_for(db, client)

        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brandnew1-longer"})
        assert r.status_code == 204

        db.refresh(user)
        assert (user.token_version or 0) == old_tv + 1  # old JWTs revoked

        # login works with the new password
        r = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "brandnew1-longer"})
        assert r.status_code == 200

        # token is single-use
        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "another1-longer"})
        assert r.status_code == 400

    def test_invalid_token_rejected(self, client):
        r = client.post("/api/auth/reset-password", json={"token": "bogus", "new_password": "whatever1-longer"})
        assert r.status_code == 400

    def test_expired_token_rejected(self, client, db):
        token = _reset_token_for(db, client)
        row = db.query(models.PasswordResetToken).one()
        row.expires_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        db.commit()
        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "whatever1-longer"})
        assert r.status_code == 400

    def test_short_password_rejected(self, client, db):
        token = _reset_token_for(db, client)
        r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "abc"})
        assert r.status_code == 422
