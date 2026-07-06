"""Tests for /api/requirements, coverage, linking, import, and GraphQL."""

import io
from backend import models


def _seed(db):
    db.add_all([
        models.Test(id="TC-P1", title="Pass one", status="pass", type="manual", priority="med", auto=False, tags=[]),
        models.Test(id="TC-P2", title="Pass two", status="pass", type="manual", priority="med", auto=False, tags=[]),
        models.Test(id="TC-F1", title="Fail one", status="fail", type="manual", priority="med", auto=False, tags=[]),
        models.Test(id="TC-N1", title="Pending one", status="pending", type="manual", priority="med", auto=False, tags=[]),
    ])
    db.flush()
    r1 = models.Requirement(id="REQ-1", title="Fully covered", type="feature", status="active", priority="high")
    r2 = models.Requirement(id="REQ-2", title="At risk", type="story", status="active", priority="med")
    r3 = models.Requirement(id="REQ-3", title="Uncovered epic", type="epic", status="draft", priority="low")
    db.add_all([r1, r2, r3])
    db.flush()
    r1.tests = db.query(models.Test).filter(models.Test.id.in_(["TC-P1", "TC-P2"])).all()
    r2.tests = db.query(models.Test).filter(models.Test.id.in_(["TC-P1", "TC-F1", "TC-N1"])).all()
    db.commit()


# ── GET /api/requirements ─────────────────────────────────────────────────────

class TestListRequirements:
    def test_returns_all(self, client, db):
        _seed(db)
        r = client.get("/api/requirements")
        assert r.status_code == 200
        assert len(r.json()) == 3

    def test_filter_type(self, client, db):
        _seed(db)
        r = client.get("/api/requirements?type=epic")
        assert [x["id"] for x in r.json()] == ["REQ-3"]

    def test_filter_status(self, client, db):
        _seed(db)
        r = client.get("/api/requirements?status=draft")
        assert len(r.json()) == 1

    def test_filter_covered_true(self, client, db):
        _seed(db)
        r = client.get("/api/requirements?covered=true")
        ids = {x["id"] for x in r.json()}
        assert ids == {"REQ-1", "REQ-2"}

    def test_filter_covered_false(self, client, db):
        _seed(db)
        r = client.get("/api/requirements?covered=false")
        assert [x["id"] for x in r.json()] == ["REQ-3"]

    def test_search(self, client, db):
        _seed(db)
        r = client.get("/api/requirements?search=risk")
        assert [x["id"] for x in r.json()] == ["REQ-2"]

    def test_empty_db(self, client, db):
        r = client.get("/api/requirements")
        assert r.json() == []


# ── coverage math ─────────────────────────────────────────────────────────────

class TestCoverage:
    def test_fully_covered(self, client, db):
        _seed(db)
        c = client.get("/api/requirements/REQ-1").json()["coverage"]
        assert c == {"linked": 2, "passed": 2, "failed": 0, "untested": 0, "pass_rate": 1.0}

    def test_at_risk_mixed(self, client, db):
        _seed(db)
        c = client.get("/api/requirements/REQ-2").json()["coverage"]
        assert c["linked"] == 3
        assert c["passed"] == 1
        assert c["failed"] == 1
        assert c["untested"] == 1
        assert c["pass_rate"] == round(1 / 3, 4)

    def test_uncovered(self, client, db):
        _seed(db)
        c = client.get("/api/requirements/REQ-3").json()["coverage"]
        assert c == {"linked": 0, "passed": 0, "failed": 0, "untested": 0, "pass_rate": 0.0}


# ── GET /{id} ─────────────────────────────────────────────────────────────────

class TestGetRequirement:
    def test_returns_with_test_ids(self, client, db):
        _seed(db)
        r = client.get("/api/requirements/REQ-1")
        assert r.status_code == 200
        assert set(r.json()["test_ids"]) == {"TC-P1", "TC-P2"}

    def test_404(self, client, db):
        assert client.get("/api/requirements/REQ-NOPE").status_code == 404


# ── POST /api/requirements ────────────────────────────────────────────────────

class TestCreate:
    def test_creates_generated_id(self, client, db):
        r = client.post("/api/requirements", json={"title": "New feature"})
        assert r.status_code == 201
        assert r.json()["id"].startswith("REQ-")
        assert r.json()["type"] == "feature"

    def test_create_with_tests(self, client, db):
        _seed(db)
        r = client.post("/api/requirements", json={"title": "Linked", "test_ids": ["TC-P1", "TC-F1"]})
        assert r.status_code == 201
        assert r.json()["coverage"]["linked"] == 2

    def test_create_unknown_test_400(self, client, db):
        r = client.post("/api/requirements", json={"title": "Bad", "test_ids": ["TC-NOPE"]})
        assert r.status_code == 400


# ── PATCH ─────────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_update_status(self, client, db):
        _seed(db)
        r = client.patch("/api/requirements/REQ-1", json={"status": "done"})
        assert r.json()["status"] == "done"

    def test_relink_tests_replace_set(self, client, db):
        _seed(db)
        r = client.patch("/api/requirements/REQ-2", json={"test_ids": ["TC-P1"]})
        assert r.json()["coverage"] == {"linked": 1, "passed": 1, "failed": 0, "untested": 0, "pass_rate": 1.0}

    def test_clear_tests(self, client, db):
        _seed(db)
        r = client.patch("/api/requirements/REQ-1", json={"test_ids": []})
        assert r.json()["coverage"]["linked"] == 0

    def test_404(self, client, db):
        assert client.patch("/api/requirements/REQ-NOPE", json={"status": "done"}).status_code == 404


# ── link / unlink ─────────────────────────────────────────────────────────────

class TestLinkUnlink:
    def test_link(self, client, db):
        _seed(db)
        r = client.post("/api/requirements/REQ-3/tests/TC-P1")
        assert r.status_code == 200
        assert r.json()["coverage"]["linked"] == 1

    def test_link_is_idempotent(self, client, db):
        _seed(db)
        client.post("/api/requirements/REQ-1/tests/TC-P1")  # already linked
        assert client.get("/api/requirements/REQ-1").json()["coverage"]["linked"] == 2

    def test_unlink(self, client, db):
        _seed(db)
        r = client.delete("/api/requirements/REQ-1/tests/TC-P1")
        assert r.json()["coverage"]["linked"] == 1

    def test_link_unknown_test_404(self, client, db):
        _seed(db)
        assert client.post("/api/requirements/REQ-1/tests/TC-NOPE").status_code == 404

    def test_link_unknown_req_404(self, client, db):
        _seed(db)
        assert client.post("/api/requirements/REQ-NOPE/tests/TC-P1").status_code == 404


# ── GET /api/tests/{id}/requirements ──────────────────────────────────────────

class TestTestRequirements:
    def test_lists_for_test(self, client, db):
        _seed(db)
        r = client.get("/api/tests/TC-P1/requirements")
        assert r.status_code == 200
        assert {x["id"] for x in r.json()} == {"REQ-1", "REQ-2"}

    def test_empty(self, client, db):
        _seed(db)
        assert client.get("/api/tests/TC-P2/requirements").json()[0]["id"] == "REQ-1"

    def test_404_unknown_test(self, client, db):
        assert client.get("/api/tests/TC-NOPE/requirements").status_code == 404


# ── import ────────────────────────────────────────────────────────────────────

class TestImport:
    def test_yaml_import(self, client, db):
        _seed(db)
        body = b"""
- id: REQ-900
  title: Imported feature
  type: feature
  priority: high
  tests: [TC-P1, TC-NOPE]
- title: No id story
  type: story
"""
        r = client.post("/api/requirements/import", files={"file": ("r.yaml", body, "application/x-yaml")})
        assert r.status_code == 200
        data = r.json()
        assert data["imported"]["created"] == 2
        assert any("TC-NOPE" in w for w in data["warnings"])
        assert client.get("/api/requirements/REQ-900").json()["coverage"]["linked"] == 1

    def test_csv_import(self, client, db):
        _seed(db)
        body = b"id,title,type,status,tests\nREQ-901,CSV req,epic,active,TC-P1 TC-P2\n"
        r = client.post("/api/requirements/import", files={"file": ("r.csv", body, "text/csv")})
        assert r.json()["imported"]["created"] == 1
        assert client.get("/api/requirements/REQ-901").json()["coverage"]["linked"] == 2

    def test_import_upsert_by_id(self, client, db):
        _seed(db)
        body = b"- id: REQ-1\n  title: Renamed\n  type: feature\n"
        r = client.post("/api/requirements/import", files={"file": ("r.yaml", body, "application/x-yaml")})
        assert r.json()["imported"] == {"created": 0, "updated": 1, "skipped": 0}
        assert client.get("/api/requirements/REQ-1").json()["title"] == "Renamed"

    def test_import_bad_yaml_400(self, client, db):
        body = b"::: not valid : ["
        r = client.post("/api/requirements/import", files={"file": ("r.yaml", body, "application/x-yaml")})
        assert r.status_code == 400


# ── role enforcement ──────────────────────────────────────────────────────────

class TestRoles:
    def test_viewer_cannot_create(self, auth_client, db):
        c = auth_client("viewer")
        assert c.post("/api/requirements", json={"title": "X"}).status_code == 403

    def test_tester_can_create(self, auth_client, db):
        c = auth_client("tester")
        assert c.post("/api/requirements", json={"title": "X"}).status_code == 201

    def test_only_admin_deletes(self, auth_client, db):
        _seed(db)
        assert auth_client("manager").delete("/api/requirements/REQ-1").status_code == 403
        assert auth_client("admin").delete("/api/requirements/REQ-1").status_code == 204
