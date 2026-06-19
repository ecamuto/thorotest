import pytest
from backend import models


@pytest.fixture(autouse=True)
def seed_execution(db):
    """Seed run + run case + test with steps."""
    db.add(models.Test(
        id="TC-EXEC-1", title="Execution test", type="manual",
        status="pending", priority="med", auto=False, tags=[],
    ))
    db.flush()
    db.add_all([
        models.TestStep(test_id="TC-EXEC-1", order=1, action="Step 1", expected_result="Expected 1"),
        models.TestStep(test_id="TC-EXEC-1", order=2, action="Step 2", expected_result="Expected 2"),
    ])
    db.add(models.Run(
        id="R-EXEC-1", name="Exec run", status="running",
        total=1, owner="test", env="test", branch="main",
    ))
    db.flush()
    rc = models.RunCase(run_id="R-EXEC-1", test_id="TC-EXEC-1", status="pending")
    db.add(rc)
    db.commit()
    db.refresh(rc)
    # Store case id on db session for tests to read
    db.rc_id = rc.id


def test_run_case_has_actual_result():
    """RunCase table has actual_result column (migration check)."""
    from sqlalchemy import inspect
    from backend.db import engine
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("run_cases")]
    assert "actual_result" in cols, "actual_result column missing from run_cases — check _run_migrations()"


def test_list_step_results_creates_pending(db, client):
    rc_id = db.rc_id
    r = client.get(f"/api/runs/R-EXEC-1/cases/{rc_id}/steps")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(s["status"] == "pending" for s in data)


def test_update_step_result(db, client):
    rc_id = db.rc_id
    # Get steps to find step_id
    r = client.get(f"/api/runs/R-EXEC-1/cases/{rc_id}/steps")
    step_id = r.json()[0]["test_step_id"]

    r2 = client.patch(
        f"/api/runs/R-EXEC-1/cases/{rc_id}/steps/{step_id}",
        json={"status": "pass", "actual_result": "It worked"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] == "pass"
    assert data["actual_result"] == "It worked"


def test_update_step_result_fail(db, client):
    rc_id = db.rc_id
    r = client.get(f"/api/runs/R-EXEC-1/cases/{rc_id}/steps")
    step_id = r.json()[1]["test_step_id"]

    r2 = client.patch(
        f"/api/runs/R-EXEC-1/cases/{rc_id}/steps/{step_id}",
        json={"status": "fail", "actual_result": "Wrong output"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "fail"
