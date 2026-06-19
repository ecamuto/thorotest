"""Tests for GET /api/runs/{id} — enriched cases with test title/duration."""
import pytest


class TestRunDetailNotFound:
    def test_unknown_run_returns_404(self, client):
        r = client.get("/api/runs/DOES-NOT-EXIST")
        assert r.status_code == 404

    def test_404_body_has_detail(self, client):
        r = client.get("/api/runs/DOES-NOT-EXIST")
        assert "detail" in r.json()


class TestRunDetailShape:
    def test_returns_200_for_known_run(self, seeded, client):
        r = client.get("/api/runs/R-TEST")
        assert r.status_code == 200

    def test_run_fields_present(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        for field in ("id", "name", "status", "progress", "total",
                      "passed", "failed", "blocked", "owner", "env", "branch"):
            assert field in data, f"missing field: {field}"

    def test_cases_field_is_list(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        assert isinstance(data["cases"], list)

    def test_case_fields_present(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        assert len(data["cases"]) > 0
        for case in data["cases"]:
            for field in ("id", "run_id", "test_id", "status", "title", "duration"):
                assert field in case, f"case missing field: {field}"


class TestRunDetailEnrichedCases:
    # R-TEST has cases: TC-A1 (pass), TC-C1 (pass), TC-C2 (fail)
    # TC-A1: title="Login with valid creds", no duration set → "—"
    # TC-C1: title="Stripe charge succeeds", duration="00:52"
    # TC-C2: title="Cart persists (guest)", no duration set → "—"

    def test_case_title_comes_from_joined_test(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        cases_by_id = {c["test_id"]: c for c in data["cases"]}
        assert cases_by_id["TC-A1"]["title"] == "Login with valid creds"
        assert cases_by_id["TC-C1"]["title"] == "Stripe charge succeeds"

    def test_case_duration_comes_from_joined_test(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        cases_by_id = {c["test_id"]: c for c in data["cases"]}
        assert cases_by_id["TC-C1"]["duration"] == "00:52"

    def test_case_duration_fallback_when_test_has_none(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        cases_by_id = {c["test_id"]: c for c in data["cases"]}
        assert cases_by_id["TC-A1"]["duration"] == "—"

    def test_case_status_from_run_case(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        cases_by_id = {c["test_id"]: c for c in data["cases"]}
        assert cases_by_id["TC-A1"]["status"] == "pass"
        assert cases_by_id["TC-C2"]["status"] == "fail"

    def test_case_count_matches_seeded_run_cases(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        # Seeded 3 run cases for R-TEST
        assert len(data["cases"]) == 3

    def test_run_metadata_correct(self, seeded, client):
        data = client.get("/api/runs/R-TEST").json()
        assert data["id"] == "R-TEST"
        assert data["status"] == "running"
        assert data["total"] == 5
        assert data["passed"] == 2
        assert data["env"] == "staging"
        assert data["branch"] == "main"


class TestRunDetailOrphanCase:
    """Case whose test was deleted — title falls back to test_id."""

    def test_orphan_case_title_falls_back_to_test_id(self, seeded, client, db):
        from backend import models as m
        # Add a run case with a non-existent test_id
        db.add(m.RunCase(run_id="R-TEST", test_id="TC-GHOST", status="pending"))
        db.commit()

        data = client.get("/api/runs/R-TEST").json()
        ghost = next((c for c in data["cases"] if c["test_id"] == "TC-GHOST"), None)
        assert ghost is not None
        assert ghost["title"] == "TC-GHOST"
        assert ghost["duration"] == "—"
