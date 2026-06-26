"""JWT revocation via per-user token_version (see auth_utils / auth.logout)."""


def test_logout_revokes_existing_token(auth_client):
    """After logout the token used is rejected (401) on the next request."""
    tester = auth_client("tester")
    # Token works before logout.
    assert tester.get("/api/me").status_code == 200
    assert tester.post("/api/auth/logout").status_code == 204
    # Same token is now revoked.
    assert tester.get("/api/me").status_code == 401


def test_relogin_after_logout_issues_valid_token(auth_client):
    """A fresh login after logout yields a usable token."""
    tester = auth_client("tester")
    tester.post("/api/auth/logout")
    relog = tester.post("/api/auth/login", json={"email": "tester@test.com", "password": "pass123"})
    assert relog.status_code == 200
    tester.headers["Authorization"] = f"Bearer {relog.json()['access_token']}"
    assert tester.get("/api/me").status_code == 200
