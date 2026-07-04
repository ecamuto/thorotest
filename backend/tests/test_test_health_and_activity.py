"""Tests for GET /api/insights/test-health and activity-feed writes on mutations."""
from datetime import datetime, timedelta, timezone

import pytest

from backend import models


def _iso_ago(**kwargs) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


@pytest.fixture
def health_client(seeded, client):
    return client


class TestTestHealthShape:
    def test_returns_200(self, health_client):
        r = health_client.get("/api/insights/test-health")
        assert r.status_code == 200

    def test_default_window_is_14_days(self, health_client):
        data = health_client.get("/api/insights/test-health").json()
        assert len(data["days"]) == 14

    def test_days_param_respected(self, health_client):
        data = health_client.get("/api/insights/test-health?days=7").json()
        assert len(data["days"]) == 7

    def test_days_param_clamped(self, health_client):
        assert len(health_client.get("/api/insights/test-health?days=500").json()["days"]) == 90
        assert len(health_client.get("/api/insights/test-health?days=0").json()["days"]) == 1

    def test_day_entries_have_required_keys(self, health_client):
        data = health_client.get("/api/insights/test-health").json()
        for d in data["days"]:
            assert set(d.keys()) == {"date", "passed", "failed", "blocked", "skipped", "runs"}


class TestTestHealthAggregation:
    def test_runs_without_created_at_are_excluded(self, health_client):
        # seeded R-TEST has no created_at
        data = health_client.get("/api/insights/test-health").json()
        assert data["total_runs"] == 0
        assert data["totals"] == {"passed": 0, "failed": 0, "blocked": 0, "skipped": 0}

    def test_run_counters_bucketed_by_day(self, seeded, client):
        seeded.add(models.Run(id="R-H1", name="Recent", status="pass",
                              total=10, passed=7, failed=2, blocked=1,
                              created_at=_iso_ago(days=1)))
        seeded.add(models.Run(id="R-H2", name="Today", status="fail",
                              total=6, passed=3, failed=2, blocked=0,
                              created_at=_iso_ago(minutes=5)))
        seeded.commit()
        data = client.get("/api/insights/test-health").json()
        assert data["total_runs"] == 2
        assert data["totals"]["passed"] == 10
        assert data["totals"]["failed"] == 4
        assert data["totals"]["blocked"] == 1
        # R-H2: 6 - 3 - 2 - 0 = 1 skipped (finished run); R-H1: 10-7-2-1 = 0
        assert data["totals"]["skipped"] == 1
        days_with_runs = [d for d in data["days"] if d["runs"] > 0]
        assert len(days_with_runs) == 2

    def test_running_runs_report_no_skipped(self, seeded, client):
        seeded.add(models.Run(id="R-H3", name="In flight", status="running",
                              total=20, passed=5, failed=1, blocked=0,
                              created_at=_iso_ago(hours=2)))
        seeded.commit()
        data = client.get("/api/insights/test-health").json()
        # 14 pending cases must not be counted as skipped while the run is live
        assert data["totals"]["skipped"] == 0

    def test_old_runs_outside_window_excluded(self, seeded, client):
        seeded.add(models.Run(id="R-OLD", name="Ancient", status="pass",
                              total=5, passed=5, failed=0, blocked=0,
                              created_at=_iso_ago(days=30)))
        seeded.commit()
        data = client.get("/api/insights/test-health").json()
        assert data["total_runs"] == 0

    def test_requires_auth(self, seeded, client):
        r = client.get("/api/insights/test-health", headers={"Authorization": ""})
        assert r.status_code in (401, 403)


class TestActivityWrites:
    def _activities(self, db):
        return db.query(models.Activity).order_by(models.Activity.id.desc()).all()

    def test_create_test_logs_activity(self, seeded, client):
        r = client.post("/api/tests", json={"title": "New edge case", "folder_id": "checkout"})
        assert r.status_code == 201
        a = self._activities(seeded)[0]
        assert a.what == "created"
        assert a.target == r.json()["id"]
        assert a.detail == "New edge case"
        assert a.who == "Test Admin"
        assert a.created_at is not None

    def test_status_update_logs_marked(self, seeded, client):
        r = client.patch("/api/tests/TC-A1", json={"status": "fail"})
        assert r.status_code == 200
        a = self._activities(seeded)[0]
        assert a.what == "marked"
        assert a.target == "TC-A1"
        assert "as fail" in a.detail

    def test_non_status_update_logs_edited(self, seeded, client):
        r = client.patch("/api/tests/TC-A1", json={"priority": "low"})
        assert r.status_code == 200
        a = self._activities(seeded)[0]
        assert a.what == "edited"
        assert a.target == "TC-A1"

    def test_delete_test_logs_activity(self, seeded, client):
        r = client.delete("/api/tests/TC-C3")
        assert r.status_code == 204
        a = self._activities(seeded)[0]
        assert a.what == "deleted"
        assert a.target == "TC-C3"

    def test_create_run_logs_and_sets_created_at(self, seeded, client):
        r = client.post("/api/runs", json={"id": "R-NEW", "name": "Sprint check", "test_ids": ["TC-A1"]})
        assert r.status_code == 201
        assert r.json()["created_at"] is not None
        a = self._activities(seeded)[0]
        assert a.what == "started run"
        assert a.target == "R-NEW"

    def test_complete_run_logs_activity(self, seeded, client):
        r = client.patch("/api/runs/R-TEST/status?status=completed")
        assert r.status_code == 200
        a = self._activities(seeded)[0]
        assert a.what == "completed run"
        assert a.target == "R-TEST"

    def test_create_defect_logs_activity(self, seeded, client):
        r = client.post("/api/defects", json={"title": "Broken thing", "severity": "high"})
        assert r.status_code == 201
        a = self._activities(seeded)[0]
        assert a.what == "filed defect"
        assert a.target == r.json()["id"]
        assert a.detail == "Broken thing"

    def test_initial_data_activity_includes_created_at(self, seeded, client):
        client.post("/api/tests", json={"title": "T", "folder_id": "checkout"})
        data = client.get("/api/initial-data").json()
        newest = data["activity"][0]
        assert newest["created_at"] is not None
        assert newest["what"] == "created"
