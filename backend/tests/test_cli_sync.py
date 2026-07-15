"""Tests for POST /api/sync/yaml — the CLI-facing YAML sync endpoint."""
import pytest

from backend import models


VALID_YAML = """\
id: TC-9001
title: "Login succeeds with valid credentials"
type: automated
runner: playwright
priority: high
tags: [smoke, auth]
folder: Auth/Login
"""

VALID_YAML_NO_ID = """\
title: Manual smoke check
type: manual
"""

INVALID_YAML = "id: TC-9002\ntype: manual\n"  # missing title


def _payload(**over):
    body = {"files": [{"path": "tests/login.yaml", "content": VALID_YAML}]}
    body.update(over)
    return body


# ── happy path ──────────────────────────────────────────────────

def test_sync_creates_test(client, db):
    r = client.post("/api/sync/yaml", json=_payload())
    assert r.status_code == 200
    stats = r.json()
    assert stats["created"] == 1
    assert stats["updated"] == 0
    assert stats["skipped"] == 0
    assert stats["files"] == 1
    assert stats["dry_run"] is False

    t = db.query(models.Test).filter(models.Test.id == "TC-9001").first()
    assert t is not None
    assert t.title == "Login succeeds with valid credentials"
    assert t.type == "automated"
    assert t.auto is True
    assert t.priority == "high"
    assert t.tags == ["smoke", "auth"]
    assert t.repo_url == "cli://local"
    assert t.source_path == "tests/login.yaml"
    assert t.source_ref == "cli"


def test_sync_is_idempotent_by_id(client, db):
    client.post("/api/sync/yaml", json=_payload())
    r = client.post("/api/sync/yaml", json=_payload())
    assert r.status_code == 200
    assert r.json()["created"] == 0
    assert r.json()["updated"] == 1
    assert db.query(models.Test).filter(models.Test.id == "TC-9001").count() == 1


def test_sync_matches_by_source_path_when_no_id(client, db):
    body = {"files": [{"path": "tests/manual.yaml", "content": VALID_YAML_NO_ID}]}
    client.post("/api/sync/yaml", json=body)
    r = client.post("/api/sync/yaml", json=body)
    assert r.json()["updated"] == 1
    assert db.query(models.Test).filter(
        models.Test.source_path == "tests/manual.yaml").count() == 1


def test_sync_creates_folder_hierarchy(client, db):
    client.post("/api/sync/yaml", json=_payload())
    names = {f.name for f in db.query(models.Folder).all()}
    assert {"Auth", "Login"} <= names


def test_sync_never_applies_status_from_yaml(client, db):
    yaml_with_status = VALID_YAML + "status: passed\n"
    client.post("/api/sync/yaml",
                json={"files": [{"path": "t.yaml", "content": yaml_with_status}]})
    t = db.query(models.Test).filter(models.Test.id == "TC-9001").first()
    assert t.status != "pass"  # stays at the model default, not the YAML value


def test_sync_custom_ref_and_source(client, db):
    r = client.post("/api/sync/yaml", json=_payload(
        ref="v1.2.3", source="cli://ci-runner/suite"))
    assert r.status_code == 200
    t = db.query(models.Test).filter(models.Test.id == "TC-9001").first()
    assert t.source_ref == "v1.2.3"
    assert t.repo_url == "cli://ci-runner/suite"


# ── dry run ─────────────────────────────────────────────────────

def test_dry_run_reports_but_does_not_persist(client, db):
    db.commit()  # persist fixture rows: dry-run rolls back the shared test session
    r = client.post("/api/sync/yaml", json=_payload(dry_run=True))
    assert r.status_code == 200
    stats = r.json()
    assert stats["created"] == 1
    assert stats["dry_run"] is True
    assert db.query(models.Test).filter(models.Test.id == "TC-9001").count() == 0


def test_dry_run_then_real_sync(client, db):
    db.commit()  # persist fixture rows: dry-run rolls back the shared test session
    client.post("/api/sync/yaml", json=_payload(dry_run=True))
    r = client.post("/api/sync/yaml", json=_payload())
    assert r.json()["created"] == 1
    assert db.query(models.Test).filter(models.Test.id == "TC-9001").count() == 1


# ── invalid input ───────────────────────────────────────────────

def test_invalid_yaml_is_skipped_with_warning(client, db):
    r = client.post("/api/sync/yaml", json={"files": [
        {"path": "bad.yaml", "content": INVALID_YAML},
        {"path": "good.yaml", "content": VALID_YAML},
    ]})
    assert r.status_code == 200
    stats = r.json()
    assert stats["created"] == 1
    assert stats["skipped"] == 1
    assert any("bad.yaml" in w for w in stats["warnings"])


def test_empty_files_list_rejected(client):
    r = client.post("/api/sync/yaml", json={"files": []})
    assert r.status_code == 422


def test_duplicate_paths_rejected(client):
    r = client.post("/api/sync/yaml", json={"files": [
        {"path": "a.yaml", "content": VALID_YAML},
        {"path": "a.yaml", "content": VALID_YAML},
    ]})
    assert r.status_code == 422


def test_oversized_file_rejected(client):
    big = VALID_YAML + "# " + "x" * (256 * 1024)
    r = client.post("/api/sync/yaml", json={"files": [{"path": "big.yaml", "content": big}]})
    assert r.status_code == 413


def test_source_must_be_cli_scheme(client):
    r = client.post("/api/sync/yaml", json=_payload(source="https://github.com/a/b"))
    assert r.status_code == 422


# ── auth ────────────────────────────────────────────────────────

def test_sync_requires_auth(db):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db import get_db

    def override():
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        r = c.post("/api/sync/yaml", json=_payload())
    app.dependency_overrides.clear()
    assert r.status_code in (401, 403)


def test_sync_rejects_viewer_role(auth_client):
    c = auth_client("viewer")
    r = c.post("/api/sync/yaml", json=_payload())
    assert r.status_code == 403
