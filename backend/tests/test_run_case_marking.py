"""Manual case marking: PATCH /runs/{id}/cases/{case_id} with a status
recomputes the run's counters/progress/status. This is the real-time run
path — the same values the WebSocket broadcasts to viewers."""
import pytest
from backend import models


@pytest.fixture
def seed_run(db):
    db.add(models.Test(id="TC-M1", title="Case one", type="manual",
                       status="pending", priority="med", auto=False, tags=[]))
    db.add(models.Test(id="TC-M2", title="Case two", type="manual",
                       status="pending", priority="med", auto=False, tags=[]))
    db.add(models.Run(id="R-MARK", name="Mark run", status="pending", total=2))
    db.flush()
    c1 = models.RunCase(run_id="R-MARK", test_id="TC-M1", status="pending")
    c2 = models.RunCase(run_id="R-MARK", test_id="TC-M2", status="pending")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1); db.refresh(c2)
    return c1.id, c2.id


def test_mark_pass_sets_running_and_counts(seed_run, client):
    c1, _ = seed_run
    r = client.patch(f"/api/runs/R-MARK/cases/{c1}", json={"status": "pass", "actual_result": "ok"})
    assert r.status_code == 200
    assert r.json()["status"] == "pass"
    run = client.get("/api/runs/R-MARK").json()
    assert run["passed"] == 1 and run["failed"] == 0
    assert run["status"] == "running"          # not complete yet
    assert run["progress"] == 50


def test_mark_all_completes_run(seed_run, client):
    c1, c2 = seed_run
    client.patch(f"/api/runs/R-MARK/cases/{c1}", json={"status": "pass"})
    client.patch(f"/api/runs/R-MARK/cases/{c2}", json={"status": "fail"})
    run = client.get("/api/runs/R-MARK").json()
    assert run["passed"] == 1 and run["failed"] == 1
    assert run["progress"] == 100
    assert run["status"] == "fail"             # any failure → run fails


def test_all_pass_run_passes(seed_run, client):
    c1, c2 = seed_run
    client.patch(f"/api/runs/R-MARK/cases/{c1}", json={"status": "pass"})
    client.patch(f"/api/runs/R-MARK/cases/{c2}", json={"status": "pass"})
    run = client.get("/api/runs/R-MARK").json()
    assert run["status"] == "pass" and run["progress"] == 100


def test_invalid_status_rejected(seed_run, client):
    c1, _ = seed_run
    r = client.patch(f"/api/runs/R-MARK/cases/{c1}", json={"status": "bogus"})
    assert r.status_code == 400


def test_actual_result_persists(seed_run, client):
    c1, _ = seed_run
    client.patch(f"/api/runs/R-MARK/cases/{c1}", json={"status": "fail", "actual_result": "boom"})
    run = client.get("/api/runs/R-MARK").json()
    case = next(c for c in run["cases"] if c["id"] == c1)
    assert case["status"] == "fail"
