"""Tests for GET /api/initial-data — all views now depend on this endpoint."""
import pytest


class TestInitialDataShape:
    def test_returns_200(self, seeded, client):
        r = client.get("/api/initial-data")
        assert r.status_code == 200

    def test_has_all_top_level_keys(self, seeded, client):
        data = client.get("/api/initial-data").json()
        assert set(data.keys()) >= {"folders", "tests", "runs", "pipelines", "activity", "defects"}

    def test_all_values_are_lists(self, seeded, client):
        data = client.get("/api/initial-data").json()
        for key in ("folders", "tests", "runs", "pipelines", "activity", "defects"):
            assert isinstance(data[key], list), f"{key} should be a list"


class TestInitialDataTests:
    """Tests list must use frontend-normalized field names."""

    def test_tests_not_empty(self, seeded, client):
        data = client.get("/api/initial-data").json()
        assert len(data["tests"]) == 5

    def test_test_has_folder_not_folder_id(self, seeded, client):
        data = client.get("/api/initial-data").json()
        t = data["tests"][0]
        assert "folder" in t, "should expose 'folder', not 'folder_id'"
        assert "folder_id" not in t

    def test_test_has_updated_not_updated_at(self, seeded, client):
        data = client.get("/api/initial-data").json()
        t = data["tests"][0]
        assert "updated" in t, "should expose 'updated', not 'updated_at'"
        assert "updated_at" not in t

    def test_test_has_lastRun_not_last_run_at(self, seeded, client):
        data = client.get("/api/initial-data").json()
        t = data["tests"][0]
        assert "lastRun" in t, "should expose 'lastRun', not 'last_run_at'"
        assert "last_run_at" not in t

    def test_test_has_required_fields(self, seeded, client):
        data = client.get("/api/initial-data").json()
        t = next(x for x in data["tests"] if x["id"] == "TC-A1")
        assert t["title"] == "Login with valid creds"
        assert t["status"] == "pass"
        assert t["type"] == "manual"
        assert t["priority"] == "high"
        assert t["auto"] is False
        assert isinstance(t["tags"], list)

    def test_auto_test_has_runner(self, seeded, client):
        data = client.get("/api/initial-data").json()
        t = next(x for x in data["tests"] if x["id"] == "TC-A2")
        assert t["auto"] is True
        assert t["runner"] == "playwright"


class TestInitialDataFolders:
    """Folder tree must be nested for the Library sidebar."""

    def test_only_top_level_folders_at_root(self, seeded, client):
        data = client.get("/api/initial-data").json()
        # auth and checkout are top-level; auth-login is a child
        root_ids = [f["id"] for f in data["folders"]]
        assert "auth" in root_ids
        assert "checkout" in root_ids
        assert "auth-login" not in root_ids

    def test_child_folders_nested_under_parent(self, seeded, client):
        data = client.get("/api/initial-data").json()
        auth = next(f for f in data["folders"] if f["id"] == "auth")
        child_ids = [c["id"] for c in auth.get("children", [])]
        assert "auth-login" in child_ids

    def test_folder_has_required_fields(self, seeded, client):
        data = client.get("/api/initial-data").json()
        f = data["folders"][0]
        assert "id" in f
        assert "name" in f
        assert "count" in f


class TestInitialDataRuns:
    def test_runs_not_empty(self, seeded, client):
        data = client.get("/api/initial-data").json()
        assert len(data["runs"]) >= 1

    def test_run_has_required_fields(self, seeded, client):
        data = client.get("/api/initial-data").json()
        r = data["runs"][0]
        for field in ("id", "name", "status", "progress", "total",
                      "passed", "failed", "blocked"):
            assert field in r, f"run missing field: {field}"


class TestInitialDataEmpty:
    def test_empty_db_returns_empty_lists(self, client):
        data = client.get("/api/initial-data").json()
        assert data["tests"] == []
        assert data["runs"] == []
        assert data["folders"] == []
        assert data["pipelines"] == []
        assert data["activity"] == []
        assert data["defects"] == []
