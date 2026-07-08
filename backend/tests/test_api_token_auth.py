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
