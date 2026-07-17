"""Password policy (SECURITY M-5 / roadmap Q-4): ≥12 chars, common-password
blocklist, no own-identifier reuse — enforced at every endpoint that sets a
password (register, me/password, reset-password, admin create)."""
import pytest
from fastapi import HTTPException

from backend.auth_utils import validate_password


class TestValidatePassword:
    def test_accepts_long_password(self):
        validate_password("correct-horse-battery")  # no raise

    def test_rejects_11_chars(self):
        with pytest.raises(HTTPException) as e:
            validate_password("elevenchars")
        assert e.value.status_code == 422
        assert "12" in e.value.detail

    def test_rejects_over_128(self):
        with pytest.raises(HTTPException) as e:
            validate_password("x" * 129)
        assert e.value.status_code == 422

    def test_rejects_common_password(self):
        with pytest.raises(HTTPException) as e:
            validate_password("Password12345")
        assert e.value.status_code == 422

    def test_rejects_single_repeated_char(self):
        with pytest.raises(HTTPException) as e:
            validate_password("aaaaaaaaaaaa")
        assert e.value.status_code == 422

    def test_rejects_password_containing_username(self):
        with pytest.raises(HTTPException) as e:
            validate_password("marco-rossi-2026", username="marco")
        assert e.value.status_code == 422

    def test_rejects_password_containing_email_local_part(self):
        with pytest.raises(HTTPException) as e:
            validate_password("enzo.camuto+pw!", email="enzo.camuto@example.com")
        assert e.value.status_code == 422

    def test_short_username_not_matched(self):
        # identifiers under 4 chars are ignored (too many false positives)
        validate_password("abcdefgh1234", username="abc")


class TestPolicyAtEndpoints:
    def test_register_rejects_short(self, client):
        r = client.post("/api/auth/register", json={
            "username": "polly", "email": "polly@test.com", "password": "short1",
        })
        assert r.status_code == 422

    def test_me_password_rejects_short(self, auth_client):
        tester = auth_client("tester")
        r = tester.put("/api/me/password", json={
            "current_password": "pass123", "new_password": "short1",
        })
        assert r.status_code == 422

    def test_admin_create_rejects_short(self, auth_client):
        admin = auth_client("admin")
        r = admin.post("/api/admin/users", json={
            "username": "shorty", "email": "shorty@test.com",
            "password": "short1", "role": "tester",
        })
        assert r.status_code == 422
