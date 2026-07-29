"""API tokens (th_…) authenticate programmatic callers (CI/scripts) as the
user who created them. Previously they were created but never validated."""
import hashlib
from backend import models


def _create_token(client, name="ci", scope="write"):
    r = client.post("/api/tokens", json={"name": name, "scope": scope})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_token_authenticates_as_creator(client):
    raw = _create_token(client)
    # Use the raw token instead of the admin JWT the fixture sends by default.
    me = client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@test.com"   # the creating admin


def test_token_grants_write_access(client):
    raw = _create_token(client)
    r = client.post("/api/tests", headers={"Authorization": f"Bearer {raw}"},
                    json={"id": "TC-TOK", "title": "made via token"})
    assert r.status_code == 201


def test_revoked_token_rejected(client):
    raw = _create_token(client)
    tok_id = client.get("/api/tokens").json()[0]["id"]
    assert client.delete(f"/api/tokens/{tok_id}").status_code == 204
    me = client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 401


def test_bogus_token_rejected(client):
    me = client.get("/api/me", headers={"Authorization": "Bearer th_not_a_real_token"})
    assert me.status_code == 401


def test_ownerless_token_rejected(client, db):
    # A legacy token with no user_id must not authenticate.
    raw = "th_legacy_orphan"
    db.add(models.ApiToken(
        name="legacy", token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        token_prefix=raw[:12], scope="", user_id=None,
    ))
    db.commit()
    me = client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 401


def test_last_used_stamped(client, db):
    raw = _create_token(client)
    client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    tok = db.query(models.ApiToken).first()
    assert tok.last_used_at is not None


# ── Scope, expiry, revocation (SECURITY H-2) ─────────────────────────────────

def test_read_scope_allows_safe_methods(client):
    raw = _create_token(client, scope="read")
    r = client.get("/api/tests", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200


def test_read_scope_blocks_writes(client):
    """scope was previously stored and displayed but never checked, so a token
    labelled read-only carried its owner's full write access."""
    raw = _create_token(client, scope="read")
    r = client.post("/api/tests", headers={"Authorization": f"Bearer {raw}"},
                    json={"id": "TC-RO", "title": "should not be created"})
    assert r.status_code == 403
    assert "read-only" in r.json()["detail"].lower()


def test_read_scope_blocks_delete(client):
    raw = _create_token(client, scope="read")
    r = client.delete("/api/tests/TC-ANY", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 403


def test_invalid_scope_rejected(client):
    r = client.post("/api/tokens", json={"name": "bad", "scope": "superuser"})
    assert r.status_code == 422


def test_token_gets_expiry_by_default(client, db):
    _create_token(client)
    tok = db.query(models.ApiToken).first()
    assert tok.expires_at is not None


def test_expired_token_rejected(client, db):
    from datetime import datetime, timedelta, timezone
    raw = _create_token(client)
    tok = db.query(models.ApiToken).first()
    tok.expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    db.commit()
    me = client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 401


def test_password_reset_revokes_api_tokens(client, db):
    """Bumping token_version ("log out everywhere" / password reset) must
    invalidate API tokens too, not just JWTs."""
    raw = _create_token(client)
    assert client.get("/api/me", headers={"Authorization": f"Bearer {raw}"}).status_code == 200

    user = db.query(models.User).filter(models.User.email == "admin@test.com").first()
    user.token_version = (user.token_version or 0) + 1
    db.commit()

    me = client.get("/api/me", headers={"Authorization": f"Bearer {raw}"})
    assert me.status_code == 401


def test_non_admin_sees_only_own_tokens(client, auth_client, db):
    _create_token(client, name="admin-token")
    tester = auth_client("tester")
    r = tester.post("/api/tokens", json={"name": "mine", "scope": "write"})
    assert r.status_code == 201

    listed = tester.get("/api/tokens").json()
    assert [t["name"] for t in listed] == ["mine"]


def test_viewer_cannot_mint_write_token(auth_client):
    viewer = auth_client("viewer")
    r = viewer.post("/api/tokens", json={"name": "escalate", "scope": "write"})
    assert r.status_code == 403
    assert viewer.post("/api/tokens", json={"name": "ro", "scope": "read"}).status_code == 201
