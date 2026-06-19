import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.db import get_db
from backend import models
from backend.auth_utils import hash_password, create_access_token


@pytest.fixture
def admin_client(db):
    user = models.User(username="adm", email="adm@t.com",
                       hashed_password=hash_password("x"), role="admin")
    db.add(user)
    db.flush()
    token = create_access_token(user.id)
    app.dependency_overrides[get_db] = lambda: (yield db)
    c = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def tester_client_for_assign(db):
    user = models.User(username="tstr", email="tstr@t.com",
                       hashed_password=hash_password("x"), role="tester")
    db.add(user)
    db.flush()
    token = create_access_token(user.id)
    app.dependency_overrides[get_db] = lambda: (yield db)
    c = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    yield c
    app.dependency_overrides.clear()


@pytest.fixture
def run_with_case(db):
    test = models.Test(id="TC-A1", title="Assign me")
    run = models.Run(id="R-ASSIGN", name="Assignment run", status="running", total=1)
    db.add_all([test, run])
    db.flush()
    rc = models.RunCase(run_id="R-ASSIGN", test_id="TC-A1", status="pending")
    db.add(rc)
    db.commit()
    db.refresh(rc)
    return rc


class TestAssignment:
    def test_admin_can_assign_tester(self, admin_client, run_with_case, db):
        case_id = run_with_case.id
        resp = admin_client.patch(f"/api/runs/R-ASSIGN/cases/{case_id}",
                                  json={"assigned_to": "bob"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["assigned_to"] == "bob"

    def test_tester_cannot_assign(self, tester_client_for_assign, run_with_case, db):
        case_id = run_with_case.id
        resp = tester_client_for_assign.patch(f"/api/runs/R-ASSIGN/cases/{case_id}",
                                               json={"assigned_to": "someone"})
        assert resp.status_code == 403

    def test_assign_nonexistent_case_returns_404(self, admin_client, db):
        run = models.Run(id="R-X", name="X", status="running", total=0)
        db.add(run)
        db.commit()
        resp = admin_client.patch("/api/runs/R-X/cases/99999", json={"assigned_to": "bob"})
        assert resp.status_code == 404

    def test_unassign_sets_null(self, admin_client, run_with_case, db):
        case_id = run_with_case.id
        admin_client.patch(f"/api/runs/R-ASSIGN/cases/{case_id}", json={"assigned_to": "bob"})
        resp = admin_client.patch(f"/api/runs/R-ASSIGN/cases/{case_id}",
                                  json={"assigned_to": None})
        assert resp.status_code == 200
        assert resp.json()["assigned_to"] is None


class TestMyCases:
    def test_my_cases_returns_grouped_by_run(self, db):
        # Create user and a running run with an assignment
        user = models.User(username="mycases_user", email="mc@t.com",
                           hashed_password=hash_password("x"), role="tester")
        db.add(user)
        db.flush()
        token = create_access_token(user.id)
        app.dependency_overrides[get_db] = lambda: (yield db)
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        test = models.Test(id="TC-MC1", title="My case")
        run = models.Run(id="R-MC", name="Active run", status="running", total=1)
        db.add_all([test, run])
        db.flush()
        rc = models.RunCase(run_id="R-MC", test_id="TC-MC1", status="pending",
                            assigned_to="mycases_user")
        db.add(rc)
        db.commit()

        resp = client.get("/api/runs/my-cases")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["run"]["id"] == "R-MC"
        assert len(data[0]["cases"]) == 1
        assert data[0]["cases"][0]["assigned_to"] == "mycases_user"

    def test_my_cases_excludes_completed_runs(self, db):
        user = models.User(username="mc_user2", email="mc2@t.com",
                           hashed_password=hash_password("x"), role="tester")
        db.add(user)
        db.flush()
        token = create_access_token(user.id)
        app.dependency_overrides[get_db] = lambda: (yield db)
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        test = models.Test(id="TC-MC2", title="Done case")
        run = models.Run(id="R-MC2", name="Completed run", status="completed", total=1)
        db.add_all([test, run])
        db.flush()
        db.add(models.RunCase(run_id="R-MC2", test_id="TC-MC2", status="pass",
                              assigned_to="mc_user2"))
        db.commit()

        resp = client.get("/api/runs/my-cases")
        app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json() == []
