"""Tests for /api/defects and /api/runs/{id}/defects endpoints."""

import pytest
from backend import models


# ── helpers ──────────────────────────────────────────────────────────────────

def _seed_defects(db):
    db.add(models.Folder(id="f1", name="Auth", count=0))
    db.add(models.Test(id="TC-D1", title="Login test", folder_id="f1", type="manual",
                       status="pass", priority="med", auto=False, tags=[]))
    db.add(models.Run(id="R-D1", name="Smoke run", status="pass",
                      progress=100, total=1, passed=1, failed=0, blocked=0))
    db.flush()
    db.add_all([
        models.Defect(id="BUG-100", title="Login broken", status="open", severity="critical",
                      test_id="TC-D1", description="Steps: go to /login, submit.", created_at="1d", created_by="Marco"),
        models.Defect(id="BUG-101", title="Cart race", status="in_progress", severity="high",
                      test_id="TC-D1", run_id="R-D1"),
        models.Defect(id="BUG-102", title="Old CSS", status="closed", severity="low",
                      run_id="R-D1"),
        models.Defect(id="BUG-103", title="Tooltip flicker", status="resolved", severity="low"),
    ])
    db.commit()


# ── GET /api/defects ──────────────────────────────────────────────────────────

class TestListDefects:
    def test_returns_all(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects")
        assert r.status_code == 200
        assert len(r.json()) == 4

    def test_filter_status_open(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?status=open")
        data = r.json()
        assert all(d["status"] == "open" for d in data)
        assert len(data) == 1

    def test_filter_status_all(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?status=all")
        assert len(r.json()) == 4

    def test_filter_severity(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?severity=low")
        data = r.json()
        assert all(d["severity"] == "low" for d in data)
        assert len(data) == 2

    def test_filter_test_id(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?test_id=TC-D1")
        data = r.json()
        assert len(data) == 2
        assert all(d["test_id"] == "TC-D1" for d in data)

    def test_search_by_title(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?search=login")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "BUG-100"

    def test_search_by_id(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?search=BUG-102")
        assert len(r.json()) == 1

    def test_empty_db_returns_empty_list(self, client, db):
        r = client.get("/api/defects")
        assert r.status_code == 200
        assert r.json() == []

    def test_combined_filters(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects?severity=high&status=in_progress")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "BUG-101"


# ── GET /api/defects/{id} ─────────────────────────────────────────────────────

class TestGetDefect:
    def test_returns_defect(self, client, db):
        _seed_defects(db)
        r = client.get("/api/defects/BUG-100")
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == "BUG-100"
        assert d["title"] == "Login broken"
        assert d["description"] == "Steps: go to /login, submit."
        assert d["created_at"] == "1d"
        assert d["created_by"] == "Marco"

    def test_404_unknown(self, client, db):
        r = client.get("/api/defects/BUG-9999")
        assert r.status_code == 404


# ── POST /api/defects ─────────────────────────────────────────────────────────

class TestCreateDefect:
    def test_creates_with_generated_id(self, client, db):
        r = client.post("/api/defects", json={"title": "New bug", "severity": "med"})
        assert r.status_code == 201
        d = r.json()
        assert d["id"].startswith("BUG-")
        assert d["status"] == "open"
        assert d["title"] == "New bug"

    def test_creates_with_description(self, client, db):
        r = client.post("/api/defects", json={
            "title": "Described bug",
            "severity": "high",
            "description": "Happens on mobile only.",
        })
        assert r.status_code == 201
        assert r.json()["description"] == "Happens on mobile only."

    def test_creates_linked_to_test_and_run(self, client, db):
        _seed_defects(db)
        r = client.post("/api/defects", json={
            "title": "Linked bug",
            "severity": "high",
            "test_id": "TC-D1",
            "run_id": "R-D1",
        })
        assert r.status_code == 201
        d = r.json()
        assert d["test_id"] == "TC-D1"
        assert d["run_id"] == "R-D1"

    def test_default_severity_med(self, client, db):
        r = client.post("/api/defects", json={"title": "Default sev"})
        assert r.status_code == 201
        assert r.json()["severity"] == "med"

    def test_id_uniqueness_on_collision(self, client, db):
        """Two rapid creates must produce different IDs."""
        r1 = client.post("/api/defects", json={"title": "Bug one"})
        r2 = client.post("/api/defects", json={"title": "Bug two"})
        assert r1.status_code == r2.status_code == 201
        assert r1.json()["id"] != r2.json()["id"]


# ── PATCH /api/defects/{id} ───────────────────────────────────────────────────

class TestUpdateDefect:
    def test_update_status(self, client, db):
        _seed_defects(db)
        r = client.patch("/api/defects/BUG-100", json={"status": "in_progress"})
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"

    def test_update_severity(self, client, db):
        _seed_defects(db)
        r = client.patch("/api/defects/BUG-100", json={"severity": "low"})
        assert r.status_code == 200
        assert r.json()["severity"] == "low"

    def test_update_title(self, client, db):
        _seed_defects(db)
        r = client.patch("/api/defects/BUG-100", json={"title": "Updated title"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated title"

    def test_update_description(self, client, db):
        _seed_defects(db)
        r = client.patch("/api/defects/BUG-100", json={"description": "New description"})
        assert r.status_code == 200
        assert r.json()["description"] == "New description"

    def test_partial_update_leaves_other_fields(self, client, db):
        _seed_defects(db)
        r = client.patch("/api/defects/BUG-100", json={"status": "closed"})
        d = r.json()
        assert d["severity"] == "critical"
        assert d["title"] == "Login broken"

    def test_404_unknown(self, client, db):
        r = client.patch("/api/defects/BUG-9999", json={"status": "closed"})
        assert r.status_code == 404

    def test_resolve_then_reopen(self, client, db):
        _seed_defects(db)
        client.patch("/api/defects/BUG-100", json={"status": "resolved"})
        r = client.patch("/api/defects/BUG-100", json={"status": "open"})
        assert r.json()["status"] == "open"


# ── DELETE /api/defects/{id} ──────────────────────────────────────────────────

class TestDeleteDefect:
    def test_deletes(self, client, db):
        _seed_defects(db)
        r = client.delete("/api/defects/BUG-100")
        assert r.status_code == 204
        assert client.get("/api/defects/BUG-100").status_code == 404

    def test_list_shrinks_after_delete(self, client, db):
        _seed_defects(db)
        before = len(client.get("/api/defects").json())
        client.delete("/api/defects/BUG-100")
        after = len(client.get("/api/defects").json())
        assert after == before - 1

    def test_404_unknown(self, client, db):
        r = client.delete("/api/defects/BUG-9999")
        assert r.status_code == 404


# ── GET /api/runs/{id}/defects ────────────────────────────────────────────────

class TestRunDefects:
    def test_returns_defects_for_run(self, client, db):
        _seed_defects(db)
        r = client.get("/api/runs/R-D1/defects")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        ids = {d["id"] for d in data}
        assert "BUG-101" in ids
        assert "BUG-102" in ids

    def test_run_without_defects_returns_empty(self, client, db):
        db.add(models.Run(id="R-CLEAN", name="Clean run", status="pass",
                          progress=100, total=0, passed=0, failed=0, blocked=0))
        db.commit()
        r = client.get("/api/runs/R-CLEAN/defects")
        assert r.status_code == 200
        assert r.json() == []

    def test_404_unknown_run(self, client, db):
        r = client.get("/api/runs/R-NOPE/defects")
        assert r.status_code == 404

    def test_defect_fields_present(self, client, db):
        _seed_defects(db)
        r = client.get("/api/runs/R-D1/defects")
        d = r.json()[0]
        for field in ("id", "title", "status", "severity"):
            assert field in d
