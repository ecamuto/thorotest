"""Tests for Run management endpoints — Fase 3."""


class TestListRuns:
    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_seeded_runs(self, seeded, client):
        r = client.get("/api/runs")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_run_has_required_fields(self, seeded, client):
        runs = client.get("/api/runs").json()
        r = runs[0]
        for field in ("id", "name", "status", "progress", "total", "passed", "failed", "blocked"):
            assert field in r, f"missing field: {field}"


class TestCreateRun:
    def test_creates_run_and_returns_201(self, seeded, client):
        r = client.post("/api/runs", json={
            "id": "R-NEW", "name": "New run", "status": "pending",
            "owner": "marco", "env": "staging", "branch": "main",
            "test_ids": ["TC-A1", "TC-C1"],
        })
        assert r.status_code == 201

    def test_created_run_has_correct_fields(self, seeded, client):
        r = client.post("/api/runs", json={
            "id": "R-FLD", "name": "Field check run", "status": "pending",
            "owner": "alice", "env": "prod", "branch": "feature/x",
            "test_ids": ["TC-A1"],
        })
        data = r.json()
        assert data["id"] == "R-FLD"
        assert data["name"] == "Field check run"
        assert data["owner"] == "alice"
        assert data["env"] == "prod"
        assert data["branch"] == "feature/x"

    def test_total_defaults_to_test_count(self, seeded, client):
        r = client.post("/api/runs", json={
            "id": "R-CNT", "name": "Count run", "status": "pending",
            "test_ids": ["TC-A1", "TC-A2", "TC-C1"],
        })
        assert r.json()["total"] == 3

    def test_explicit_total_overrides_test_count(self, seeded, client):
        r = client.post("/api/runs", json={
            "id": "R-TOT", "name": "Total override", "status": "pending",
            "total": 10, "test_ids": ["TC-A1"],
        })
        assert r.json()["total"] == 10

    def test_cases_created_for_each_test(self, seeded, client):
        client.post("/api/runs", json={
            "id": "R-CASES", "name": "Case check", "status": "pending",
            "test_ids": ["TC-A1", "TC-C1", "TC-C2"],
        })
        detail = client.get("/api/runs/R-CASES").json()
        case_ids = {c["test_id"] for c in detail["cases"]}
        assert case_ids == {"TC-A1", "TC-C1", "TC-C2"}

    def test_cases_start_as_pending(self, seeded, client):
        client.post("/api/runs", json={
            "id": "R-PEND", "name": "Pending cases", "status": "pending",
            "test_ids": ["TC-A1", "TC-A2"],
        })
        detail = client.get("/api/runs/R-PEND").json()
        assert all(c["status"] == "pending" for c in detail["cases"])

    def test_duplicate_run_id_returns_409(self, seeded, client):
        r = client.post("/api/runs", json={
            "id": "R-TEST", "name": "Duplicate", "status": "pending",
            "test_ids": [],
        })
        assert r.status_code == 409

    def test_run_retrievable_after_create(self, seeded, client):
        client.post("/api/runs", json={
            "id": "R-RETR", "name": "Retrievable", "status": "pending",
            "test_ids": [],
        })
        r = client.get("/api/runs/R-RETR")
        assert r.status_code == 200
        assert r.json()["name"] == "Retrievable"

    def test_run_appears_in_list(self, seeded, client):
        client.post("/api/runs", json={
            "id": "R-LIST", "name": "Listed run", "status": "pending",
            "test_ids": [],
        })
        run_ids = [r["id"] for r in client.get("/api/runs").json()]
        assert "R-LIST" in run_ids


class TestUpdateRunStatus:
    def test_pause_run(self, seeded, client):
        r = client.patch("/api/runs/R-TEST/status?status=paused")
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

    def test_abort_run(self, seeded, client):
        r = client.patch("/api/runs/R-TEST/status?status=aborted")
        assert r.status_code == 200
        assert r.json()["status"] == "aborted"

    def test_status_persists(self, seeded, client):
        client.patch("/api/runs/R-TEST/status?status=paused")
        detail = client.get("/api/runs/R-TEST").json()
        assert detail["status"] == "paused"

    def test_response_contains_id_and_status(self, seeded, client):
        r = client.patch("/api/runs/R-TEST/status?status=aborted")
        data = r.json()
        assert data["id"] == "R-TEST"
        assert data["status"] == "aborted"

    def test_unknown_run_returns_404(self, client):
        r = client.patch("/api/runs/R-GHOST/status?status=paused")
        assert r.status_code == 404
