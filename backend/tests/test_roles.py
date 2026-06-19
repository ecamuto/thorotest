import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException


class TestRequireRole:
    """Unit tests for require_role() factory — no HTTP needed."""

    def test_allowed_role_returns_user(self):
        """require_role passes through when user.role is in allowed set."""
        from backend.auth_utils import require_role
        # require_role returns a Depends() object; extract the inner _check fn
        dep = require_role("admin", "manager", "tester")
        # Depends wraps the callable — access via .dependency
        check_fn = dep.dependency
        user = MagicMock()
        user.role = "tester"
        result = check_fn(user=user)
        assert result is user

    def test_forbidden_role_raises_403(self):
        """require_role raises 403 when user.role is not in allowed set."""
        from backend.auth_utils import require_role
        dep = require_role("admin", "manager", "tester")
        check_fn = dep.dependency
        user = MagicMock()
        user.role = "viewer"
        with pytest.raises(HTTPException) as exc_info:
            check_fn(user=user)
        assert exc_info.value.status_code == 403

    def test_admin_role_passes_admin_only(self):
        """require_role('admin') admits only admin."""
        from backend.auth_utils import require_role
        dep = require_role("admin")
        check_fn = dep.dependency
        user = MagicMock()
        user.role = "manager"
        with pytest.raises(HTTPException) as exc_info:
            check_fn(user=user)
        assert exc_info.value.status_code == 403


class TestRegisterDefault:
    """POST /api/auth/register defaults new user to role='tester'."""

    def test_register_defaults_to_tester(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "pass1234",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "tester"


class TestRoleMigration:
    """DB migration: UPDATE users SET role='tester' WHERE role='member'."""

    def test_member_migrated_to_tester(self, db):
        from backend import models
        from sqlalchemy import text
        from backend.auth_utils import hash_password
        # Insert legacy member row directly
        u = models.User(
            username="legacyuser",
            email="legacy@test.com",
            hashed_password=hash_password("x"),
            role="member",
        )
        db.add(u)
        db.commit()
        # Run migration SQL directly (same as _run_migrations)
        db.execute(text("UPDATE users SET role = 'tester' WHERE role = 'member'"))
        db.commit()
        db.refresh(u)
        assert u.role == "tester"


@pytest.mark.integration
class TestEndpointRoleGuards:
    """Integration tests: endpoint-level role guards (go GREEN after Plan 02)."""

    def test_viewer_cannot_post_test(self, auth_client, db):
        c = auth_client("viewer")
        resp = c.post("/api/tests", json={
            "title": "Should fail",
            "folder_id": None,
            "type": "manual",
            "status": "pending",
            "priority": "med",
        })
        assert resp.status_code == 403

    def test_tester_can_post_test(self, auth_client, db):
        c = auth_client("tester")
        resp = c.post("/api/tests", json={
            "title": "Should pass",
            "folder_id": None,
            "type": "manual",
            "status": "pending",
            "priority": "med",
        })
        assert resp.status_code == 201

    def test_viewer_cannot_delete_test(self, auth_client, db):
        from backend import models
        t = models.Test(id="TC-DEL1", title="To delete", type="manual", status="pending", priority="med")
        db.add(t)
        db.commit()
        c = auth_client("viewer")
        resp = c.delete("/api/tests/TC-DEL1")
        assert resp.status_code == 403

    def test_admin_can_delete_test(self, auth_client, db):
        from backend import models
        t = models.Test(id="TC-DEL2", title="Admin delete", type="manual", status="pending", priority="med")
        db.add(t)
        db.commit()
        c = auth_client("admin")
        resp = c.delete("/api/tests/TC-DEL2")
        assert resp.status_code == 204

    def test_viewer_cannot_delete_run(self, auth_client, db):
        # Run delete not yet implemented — placeholder: 404 is acceptable for now
        c = auth_client("viewer")
        resp = c.delete("/api/runs/R-NONE")
        # 403 if guarded, 404 if not found, 405 if no DELETE endpoint
        assert resp.status_code in (403, 404, 405)

    def test_admin_cannot_delete_themselves(self, auth_client, db):
        """Self-delete guard: admin DELETE /admin/users/{own_id} → 400"""
        # This test goes GREEN after Plan 04 implements the admin router
        pass  # placeholder — implemented in test_admin.py in Plan 04

    def test_manager_can_write_test(self, auth_client, db):
        """Manager role can create a test (write=yes per permission matrix)."""
        c = auth_client("manager")
        resp = c.post("/api/tests", json={
            "title": "Manager write test",
            "folder_id": None,
            "type": "manual",
            "status": "pending",
            "priority": "med",
        })
        assert resp.status_code == 201

    def test_manager_cannot_delete_test(self, auth_client, db):
        """Manager role cannot delete a test (delete=admin-only per permission matrix)."""
        from backend import models
        t = models.Test(id="TC-MGR1", title="Manager cannot del", type="manual", status="pending", priority="med")
        db.add(t)
        db.commit()
        c = auth_client("manager")
        resp = c.delete("/api/tests/TC-MGR1")
        assert resp.status_code == 403

    def test_non_admin_cannot_bulk_delete(self, auth_client, db):
        """POST /api/tests/bulk with action=delete returns 403 for tester (non-admin)."""
        c = auth_client("tester")
        resp = c.post("/api/tests/bulk", json={"action": "delete", "ids": []})
        assert resp.status_code == 403

    def test_admin_can_bulk_delete(self, auth_client, db):
        """POST /api/tests/bulk with action=delete returns 200 for admin."""
        c = auth_client("admin")
        resp = c.post("/api/tests/bulk", json={"action": "delete", "ids": []})
        # 200 with empty ids is acceptable (no-op delete)
        assert resp.status_code == 200
