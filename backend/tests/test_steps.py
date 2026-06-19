import pytest
from backend import models


@pytest.fixture(autouse=True)
def seed_test(db):
    """Seed a test with 2 steps."""
    db.add(models.Test(
        id="TC-STEP-1", title="Steps test", type="manual",
        status="pending", priority="med", auto=False, tags=[],
    ))
    db.flush()
    db.add_all([
        models.TestStep(test_id="TC-STEP-1", order=1, action="Open page", expected_result="Page loads"),
        models.TestStep(test_id="TC-STEP-1", order=2, action="Click submit", expected_result="Form submitted"),
    ])
    db.commit()


def test_list_steps(client):
    r = client.get("/api/tests/TC-STEP-1/steps")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["order"] == 1
    assert data[0]["action"] == "Open page"
    assert data[1]["order"] == 2


def test_list_steps_not_found(client):
    r = client.get("/api/tests/NONEXISTENT/steps")
    assert r.status_code == 404


def test_replace_steps(client):
    r = client.patch("/api/tests/TC-STEP-1/steps", json=[
        {"action": "Step A", "expected_result": "Result A"},
        {"action": "Step B", "expected_result": "Result B"},
        {"action": "Step C", "expected_result": None},
    ])
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert data[0]["action"] == "Step A"
    assert data[0]["order"] == 1
    assert data[2]["action"] == "Step C"
    assert data[2]["order"] == 3


def test_replace_steps_empty(client):
    """Replacing with empty list deletes all steps."""
    r = client.patch("/api/tests/TC-STEP-1/steps", json=[])
    assert r.status_code == 200
    assert r.json() == []
