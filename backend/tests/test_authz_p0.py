"""Regression tests for the P0 access-control fixes (2026-07 security audit).

Guards against the class of bug where a state-changing endpoint ships without an
auth dependency. Covers:
  - Webhooks CRUD + secret-regen + test → require authentication and admin/manager.
  - Integrations create/update/delete → require authentication and admin/manager.
  - SSRF guard rejects webhook targets that resolve to internal addresses.
  - Attachment upload cannot be used to traverse outside UPLOAD_DIR.

If any of these routes ever loses its dependency again, these tests fail.
"""
import io
import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db
from backend import models
from backend.auth_utils import hash_password, create_access_token


@pytest.fixture
def anon_client(db):
    """Unauthenticated TestClient (no Authorization header) sharing the test db."""
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def tester_client(db):
    """Authenticated TestClient with the low-privilege `tester` role."""
    user = models.User(
        username="p0_tester", email="p0tester@test.com",
        hashed_password=hash_password("pass123"), display_name="P0 Tester", role="tester",
    )
    db.add(user)
    db.flush()
    token = create_access_token(user.id)

    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c
    app.dependency_overrides.clear()


# ── Webhooks: must be authenticated ───────────────────────────────────────────

WEBHOOK_MUTATIONS = [
    ("post", "/api/webhooks", {"json": {"url": "https://example.com/h", "events": []}}),
    ("patch", "/api/webhooks/1", {"json": {"status": "paused"}}),
    ("delete", "/api/webhooks/1", {}),
    ("post", "/api/webhooks/1/regenerate-secret", {}),
    ("post", "/api/webhooks/1/test", {}),
]


@pytest.mark.parametrize("method,path,kw", WEBHOOK_MUTATIONS)
def test_webhook_mutations_reject_anonymous(anon_client, method, path, kw):
    r = getattr(anon_client, method)(path, **kw)
    assert r.status_code in (401, 403), f"{method} {path} allowed anonymous access: {r.status_code}"


def test_webhook_list_rejects_anonymous(anon_client):
    assert anon_client.get("/api/webhooks").status_code in (401, 403)


@pytest.mark.parametrize("method,path,kw", WEBHOOK_MUTATIONS)
def test_webhook_mutations_reject_tester(tester_client, method, path, kw):
    r = getattr(tester_client, method)(path, **kw)
    # tester is authenticated but not admin/manager → 403 (or 404 only if it got
    # past auth, which must not happen for a missing id — so require 403).
    assert r.status_code == 403, f"{method} {path} allowed tester: {r.status_code}"


# ── Integrations: create/update/delete must be authenticated admin/manager ────

INTEGRATION_MUTATIONS = [
    ("post", "/api/integrations", {"json": {"id": "i1", "name": "x", "type": "github"}}),
    ("patch", "/api/integrations/i1", {"json": {"name": "y"}}),
    ("delete", "/api/integrations/i1", {}),
]


@pytest.mark.parametrize("method,path,kw", INTEGRATION_MUTATIONS)
def test_integration_mutations_reject_anonymous(anon_client, method, path, kw):
    r = getattr(anon_client, method)(path, **kw)
    assert r.status_code in (401, 403), f"{method} {path} allowed anonymous: {r.status_code}"


@pytest.mark.parametrize("method,path,kw", INTEGRATION_MUTATIONS)
def test_integration_mutations_reject_tester(tester_client, method, path, kw):
    r = getattr(tester_client, method)(path, **kw)
    assert r.status_code == 403, f"{method} {path} allowed tester: {r.status_code}"


# ── SSRF guard on webhook targets ─────────────────────────────────────────────

@pytest.mark.parametrize("bad_url", [
    "http://127.0.0.1/hook",
    "http://localhost/hook",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/x",
    "http://192.168.1.1/x",
    "ftp://example.com/x",
    "file:///etc/passwd",
])
def test_create_webhook_rejects_unsafe_url(client, monkeypatch, bad_url):
    # Ensure the guard is active regardless of ambient env.
    monkeypatch.delenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", raising=False)
    r = client.post("/api/webhooks", json={"url": bad_url, "events": ["run.completed"]})
    assert r.status_code == 422, f"unsafe url {bad_url} was accepted: {r.status_code} {r.text}"


def test_create_webhook_allows_public_url(client, monkeypatch):
    monkeypatch.delenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", raising=False)
    r = client.post("/api/webhooks", json={"url": "https://example.com/hook", "events": []})
    assert r.status_code == 201, r.text


# ── Attachment path traversal ─────────────────────────────────────────────────

def _file(content=b"x", filename="a.txt"):
    return ("file", (filename, io.BytesIO(content), "text/plain"))


def test_upload_rejects_bad_entity_type(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att
    monkeypatch.setattr(att, "UPLOAD_DIR", str(tmp_path))
    r = client.post("/api/attachments",
                    data={"entity_type": "../../etc", "entity_id": "1"}, files=[_file()])
    assert r.status_code == 422


def test_upload_rejects_traversal_entity_id(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att
    monkeypatch.setattr(att, "UPLOAD_DIR", str(tmp_path))
    r = client.post("/api/attachments",
                    data={"entity_type": "test", "entity_id": "../../../evil"}, files=[_file()])
    assert r.status_code == 422


def test_upload_neutralizes_traversal_filename(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att
    monkeypatch.setattr(att, "UPLOAD_DIR", str(tmp_path))
    r = client.post("/api/attachments",
                    data={"entity_type": "test", "entity_id": "TC-1"},
                    files=[_file(content=b"pwned", filename="../../../../tmp/evil.txt")])
    assert r.status_code == 201, r.text
    # Nothing may have been written outside UPLOAD_DIR.
    written = [os.path.join(root, f) for root, _, fs in os.walk(str(tmp_path)) for f in fs]
    assert written, "file should have been stored inside UPLOAD_DIR"
    for p in written:
        assert os.path.realpath(p).startswith(os.path.realpath(str(tmp_path)))
        assert "evil.txt" in os.path.basename(p)  # basename kept, path stripped
