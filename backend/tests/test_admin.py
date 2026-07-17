import pytest


class TestAdminUserManagement:
    """Integration tests for /api/admin/users endpoints."""

    def test_list_users_admin_only(self, auth_client, db):
        """GET /admin/users returns 200 for admin, 403 for tester/viewer."""
        admin_c = auth_client("admin")
        resp = admin_c.get("/api/admin/users")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

        viewer_c = auth_client("viewer")
        resp = viewer_c.get("/api/admin/users")
        assert resp.status_code == 403

        tester_c = auth_client("tester")
        resp = tester_c.get("/api/admin/users")
        assert resp.status_code == 403

    def test_create_user_admin_only(self, auth_client, db):
        """POST /admin/users creates user for admin, 403 for tester."""
        admin_c = auth_client("admin")
        resp = admin_c.post("/api/admin/users", json={
            "username": "newbie",
            "email": "newbie@test.com",
            "password": "secure123-and-long",
            "role": "tester",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "newbie"
        assert data["role"] == "tester"

        tester_c = auth_client("tester")
        resp = tester_c.post("/api/admin/users", json={
            "username": "blocked",
            "email": "blocked@test.com",
            "password": "x",
            "role": "tester",
        })
        assert resp.status_code == 403

    def test_change_role(self, auth_client, db):
        """PATCH /admin/users/{id}/role changes role."""
        from backend import models
        from backend.auth_utils import hash_password
        # Create target user
        target = models.User(
            username="targetuser",
            email="target@test.com",
            hashed_password=hash_password("x"),
            role="tester",
        )
        db.add(target)
        db.commit()

        admin_c = auth_client("admin")
        resp = admin_c.patch(f"/api/admin/users/{target.id}/role", json={"role": "viewer"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "viewer"

    def test_delete_user(self, auth_client, db):
        """DELETE /admin/users/{id} removes user."""
        from backend import models
        from backend.auth_utils import hash_password
        target = models.User(
            username="todelete",
            email="todelete@test.com",
            hashed_password=hash_password("x"),
            role="tester",
        )
        db.add(target)
        db.commit()
        target_id = target.id

        admin_c = auth_client("admin")
        resp = admin_c.delete(f"/api/admin/users/{target_id}")
        assert resp.status_code == 204

        # Confirm gone
        assert db.query(models.User).filter(models.User.id == target_id).first() is None

    def test_cannot_delete_self(self, auth_client, db):
        """Admin cannot delete their own account."""
        from backend import models
        from backend.auth_utils import hash_password, create_access_token
        from fastapi.testclient import TestClient
        from backend.main import app
        from backend.db import get_db

        # Create admin user explicitly so we know their ID
        admin_user = models.User(
            username="selfdelete_admin",
            email="selfdelete@test.com",
            hashed_password=hash_password("x"),
            role="admin",
        )
        db.add(admin_user)
        db.flush()
        token = create_access_token(admin_user.id)

        def override_get_db():
            yield db
        app.dependency_overrides[get_db] = override_get_db
        c = TestClient(app, headers={"Authorization": f"Bearer {token}"})

        resp = c.delete(f"/api/admin/users/{admin_user.id}")
        assert resp.status_code == 400
        assert "yourself" in resp.json()["detail"].lower()
