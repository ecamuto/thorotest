"""List-endpoint pagination: limit/offset params + X-Total-Count header,
and the capped /api/initial-data payload with real totals."""
from backend import models


def _add_tests(db, n):
    for i in range(n):
        db.add(models.Test(id=f"PAG-{i:03d}", title=f"Paginated test {i}"))
    db.commit()


class TestListPagination:
    def test_default_returns_all_with_total_header(self, client, db):
        _add_tests(db, 5)
        r = client.get("/api/tests")
        assert r.status_code == 200
        assert len(r.json()) == 5
        assert r.headers["X-Total-Count"] == "5"

    def test_limit_and_offset(self, client, db):
        _add_tests(db, 5)
        r = client.get("/api/tests?limit=2&offset=1")
        assert r.status_code == 200
        rows = r.json()
        assert [t["id"] for t in rows] == ["PAG-001", "PAG-002"]
        assert r.headers["X-Total-Count"] == "5"

    def test_total_reflects_filters(self, client, db):
        _add_tests(db, 5)
        db.add(models.Test(id="ZZZ-1", title="Other test", status="pass"))
        db.commit()
        r = client.get("/api/tests?status=pass&limit=1")
        assert r.headers["X-Total-Count"] == "1"
        assert len(r.json()) == 1

    def test_limit_is_capped_at_max(self, client, db):
        from backend.routers._pagination import MAX_LIMIT
        _add_tests(db, 3)
        r = client.get(f"/api/tests?limit={MAX_LIMIT * 10}")
        assert r.status_code == 200
        assert len(r.json()) == 3  # capped limit still >= row count here

    def test_negative_limit_does_not_bypass_cap(self, client, db):
        # `LIMIT -1` in SQLite is unbounded; a negative limit must be clamped
        # to >= 1 so it cannot pull the whole table.
        _add_tests(db, 5)
        r = client.get("/api/tests?limit=-1")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.headers["X-Total-Count"] == "5"

    def test_negative_offset_clamped(self, client, db):
        _add_tests(db, 3)
        r = client.get("/api/tests?offset=-5&limit=2")
        assert r.status_code == 200
        assert [t["id"] for t in r.json()] == ["PAG-000", "PAG-001"]

    def test_runs_defects_pipelines_activity_have_header(self, client):
        for path in ("/api/runs", "/api/defects", "/api/pipelines", "/api/activity"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert "X-Total-Count" in r.headers, path


class TestInitialDataCaps:
    def test_totals_present_and_correct(self, client, db):
        _add_tests(db, 4)
        r = client.get("/api/initial-data")
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["tests"] == 4
        assert len(body["tests"]) == 4

    def test_tests_capped(self, client, db, monkeypatch):
        import backend.main as main_mod
        monkeypatch.setitem(main_mod.INITIAL_DATA_CAPS, "tests", 2)
        _add_tests(db, 5)
        r = client.get("/api/initial-data")
        body = r.json()
        assert len(body["tests"]) == 2
        assert body["totals"]["tests"] == 5
