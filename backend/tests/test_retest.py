import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import get_db
from backend import models
from backend.auth_utils import hash_password, create_access_token


@pytest.fixture
def tester_client(db):
    user = models.User(username="tester1", email="t@t.com",
                       hashed_password=hash_password("x"), role="tester")
    db.add(user)
    db.flush()
    token = create_access_token(user.id)
    app.dependency_overrides[get_db] = lambda: (yield db)
    c = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def run_with_failures(db):
    """Seed a completed run with 1 pass, 1 fail, 1 blocked case."""
    test_pass = models.Test(id="TC-001", title="Pass test")
    test_fail = models.Test(id="TC-002", title="Fail test")
    test_blocked = models.Test(id="TC-003", title="Blocked test")
    db.add_all([test_pass, test_fail, test_blocked])
    run = models.Run(id="R-SOURCE", name="Sprint 5 regression",
                     status="completed", total=3, passed=1, failed=1, blocked=1)
    db.add(run)
    db.flush()
    db.add_all([
        models.RunCase(run_id="R-SOURCE", test_id="TC-001", status="pass"),
        models.RunCase(run_id="R-SOURCE", test_id="TC-002", status="fail"),
        models.RunCase(run_id="R-SOURCE", test_id="TC-003", status="blocked"),
    ])
    db.commit()
    return run


class TestRetest:
    def test_retest_creates_run_with_only_failed_blocked(self, tester_client, run_with_failures, db):
        resp = tester_client.post("/api/runs/R-SOURCE/retest")
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Retest: Sprint 5 regression"
        assert data["source_run_id"] == "R-SOURCE"
        assert data["status"] == "running"
        assert data["total"] == 2  # fail + blocked only

    def test_retest_cases_contain_only_fail_and_blocked(self, tester_client, run_with_failures, db):
        resp = tester_client.post("/api/runs/R-SOURCE/retest")
        new_run_id = resp.json()["id"]
        cases = db.query(models.RunCase).filter(models.RunCase.run_id == new_run_id).all()
        assert len(cases) == 2
        case_test_ids = {c.test_id for c in cases}
        assert "TC-001" not in case_test_ids  # pass case excluded
        assert "TC-002" in case_test_ids
        assert "TC-003" in case_test_ids

    def test_retest_with_no_failures_returns_400(self, tester_client, db):
        run = models.Run(id="R-ALL-PASS", name="All passed", status="completed", total=1)
        db.add(run)
        test = models.Test(id="TC-OK", title="OK")
        db.add(test)
        db.flush()
        db.add(models.RunCase(run_id="R-ALL-PASS", test_id="TC-OK", status="pass"))
        db.commit()
        resp = tester_client.post("/api/runs/R-ALL-PASS/retest")
        assert resp.status_code == 400

    def test_retest_nonexistent_run_returns_404(self, tester_client, db):
        resp = tester_client.post("/api/runs/R-NOPE/retest")
        assert resp.status_code == 404
