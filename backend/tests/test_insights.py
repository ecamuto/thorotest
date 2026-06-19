"""Tests for GET /api/insights — Phase 1 new endpoint."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.db import get_db
from backend import models


@pytest.fixture
def insights_client(seeded, client):
    return client


class TestInsightsShape:
    def test_returns_200(self, insights_client):
        r = insights_client.get("/api/insights")
        assert r.status_code == 200

    def test_has_all_required_keys(self, insights_client):
        data = insights_client.get("/api/insights").json()
        assert set(data.keys()) >= {
            "total_tests", "pass_rate", "open_defects",
            "open_critical", "open_high", "automation_rate", "folder_coverage"
        }

    def test_folder_coverage_entries_have_correct_fields(self, insights_client):
        data = insights_client.get("/api/insights").json()
        for entry in data["folder_coverage"]:
            assert "name" in entry
            assert "value" in entry
            assert "mapped" in entry


class TestInsightsCalculations:
    # Seed: TC-A1 pass/manual, TC-A2 pass/auto, TC-C1 pass/auto, TC-C2 fail/auto, TC-C3 pending/manual
    # Total: 5 tests, 3 pass, 3 auto

    def test_total_tests(self, insights_client):
        data = insights_client.get("/api/insights").json()
        assert data["total_tests"] == 5

    def test_pass_rate_is_percentage_of_passing_tests(self, insights_client):
        data = insights_client.get("/api/insights").json()
        # 3 pass out of 5 = 60.0%
        assert data["pass_rate"] == 60.0

    def test_automation_rate_is_percentage_of_auto_tests(self, insights_client):
        data = insights_client.get("/api/insights").json()
        # 3 auto out of 5 = 60%
        assert data["automation_rate"] == 60

    def test_open_defects_excludes_resolved(self, insights_client):
        data = insights_client.get("/api/insights").json()
        # open=2, in_progress=1, closed=1, resolved=1 → all except "resolved" = 4
        assert data["open_defects"] == 4

    def test_open_critical_count(self, insights_client):
        data = insights_client.get("/api/insights").json()
        # BUG-1 is open+critical
        assert data["open_critical"] == 1

    def test_open_high_count(self, insights_client):
        data = insights_client.get("/api/insights").json()
        # BUG-2 open+high, BUG-3 in_progress+high
        assert data["open_high"] == 2


class TestInsightsFolderCoverage:
    # auth (top-level) + child auth-login → 2 tests (TC-A1 pass, TC-A2 pass) → 100%
    # checkout (top-level, no children) → 3 tests (TC-C1 pass, TC-C2 fail, TC-C3 pending) → 33%

    def test_only_top_level_folders_appear(self, insights_client):
        data = insights_client.get("/api/insights").json()
        names = [f["name"] for f in data["folder_coverage"]]
        assert "Authentication" in names
        assert "Checkout" in names
        assert "Login flows" not in names  # child folder must not appear

    def test_auth_coverage_includes_child_folder_tests(self, insights_client):
        data = insights_client.get("/api/insights").json()
        auth = next(f for f in data["folder_coverage"] if f["name"] == "Authentication")
        # TC-A1 and TC-A2 are in auth-login (child of auth), both pass → 100%
        assert auth["value"] == 100
        assert auth["mapped"] == "2/2"

    def test_checkout_coverage_counts_direct_children(self, insights_client):
        data = insights_client.get("/api/insights").json()
        co = next(f for f in data["folder_coverage"] if f["name"] == "Checkout")
        # TC-C1 pass, TC-C2 fail, TC-C3 pending → 1/3 = 33%
        assert co["value"] == 33
        assert co["mapped"] == "1/3"

    def test_mapped_format_is_pass_slash_total(self, insights_client):
        data = insights_client.get("/api/insights").json()
        for entry in data["folder_coverage"]:
            parts = entry["mapped"].split("/")
            assert len(parts) == 2
            assert all(p.isdigit() for p in parts)


class TestInsightsEmptyDb:
    def test_empty_db_returns_zeros(self, client):
        data = client.get("/api/insights").json()
        assert data["total_tests"] == 0
        assert data["pass_rate"] == 0
        assert data["open_defects"] == 0
        assert data["automation_rate"] == 0
        assert data["folder_coverage"] == []
