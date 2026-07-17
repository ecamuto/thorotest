"""
Tests for Phase 12 — Audit Log infrastructure.
AUDIT-01: auth events recorded
AUDIT-02: user management events recorded
AUDIT-03: test and run events recorded
AUDIT-04: role guards on GET /api/audit-log
AUDIT-05: date-range filter
"""
import pytest
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit_entries(admin_client, **params):
    """GET /api/audit-log and return entries list."""
    resp = admin_client.get("/api/audit-log", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["entries"]


# ---------------------------------------------------------------------------
# AUDIT-01: Auth events
# ---------------------------------------------------------------------------

class TestAuthEvents:
    def test_login_success_logged(self, auth_client):
        """A successful login creates a login_success audit entry."""
        # auth_client creates user + JWT without calling the login endpoint;
        # explicitly POST /api/auth/login to trigger log_event(EVT_LOGIN_SUCCESS)
        admin = auth_client("admin")
        resp = admin.post("/api/auth/login", json={"email": "admin@test.com", "password": "pass123"})
        assert resp.status_code == 200
        entries = _audit_entries(admin)
        event_types = [e["event_type"] for e in entries]
        assert "login_success" in event_types

    def test_failed_login_logged(self, client):
        """A failed login attempt creates a login_fail audit entry (before 401)."""
        resp = client.post("/api/auth/login", json={"email": "nope@example.com", "password": "wrong"})
        assert resp.status_code == 401
        entries = _audit_entries(client)
        assert any(e["event_type"] == "login_fail" for e in entries), (
            f"Expected login_fail in audit entries but got: {[e['event_type'] for e in entries]}"
        )

    def test_logout_logged(self, auth_client):
        """POST /api/auth/logout creates a logout audit entry."""
        admin = auth_client("admin")
        resp = admin.post("/api/auth/logout")
        assert resp.status_code == 204
        # Logout bumps token_version, revoking the token we just used. Re-login the
        # same admin (calling auth_client("admin") again would hit a UNIQUE email
        # constraint) to obtain a fresh token before reading the audit log.
        relog = admin.post("/api/auth/login", json={"email": "admin@test.com", "password": "pass123"})
        assert relog.status_code == 200
        admin.headers["Authorization"] = f"Bearer {relog.json()['access_token']}"
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "logout" for e in entries)

    def test_password_change_logged(self, auth_client):
        """A successful password change creates a password_change audit entry."""
        tester = auth_client("tester")
        # Route is PUT /api/me/password; auth_client sets password to "pass123"
        resp = tester.put("/api/me/password", json={"current_password": "pass123", "new_password": "NewPass123!-extra"})
        assert resp.status_code == 204
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "password_change" for e in entries)

    def test_password_change_fail_logged(self, auth_client):
        """A failed password change (wrong current password) creates a password_change_fail entry."""
        tester = auth_client("tester")
        # Route is PUT /api/me/password; "WRONG" is intentionally incorrect
        resp = tester.put("/api/me/password", json={"current_password": "WRONG", "new_password": "NewPass123!-extra"})
        assert resp.status_code in (400, 401)
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "password_change_fail" for e in entries)


# ---------------------------------------------------------------------------
# AUDIT-02: User management events
# ---------------------------------------------------------------------------

class TestUserMgmtEvents:
    def test_user_created_logged(self, auth_client):
        """Creating a user via admin endpoint logs user_created event."""
        admin = auth_client("admin")
        resp = admin.post("/api/admin/users", json={
            "username": "newuser_audit", "email": "newaudit@example.com",
            "password": "Str0ng-Audit-Pw!", "display_name": "Audit Test", "role": "tester"
        })
        assert resp.status_code == 201
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "user_created" for e in entries)

    def test_user_deleted_logged(self, auth_client, db):
        """Deleting a user via admin endpoint logs user_deleted event."""
        from backend import models
        admin = auth_client("admin")
        # Create a user to delete
        resp = admin.post("/api/admin/users", json={
            "username": "todelete_audit", "email": "todelete@example.com",
            "password": "Str0ng-Audit-Pw!", "display_name": "To Delete", "role": "viewer"
        })
        assert resp.status_code == 201
        user_id = resp.json()["id"]
        del_resp = admin.delete(f"/api/admin/users/{user_id}")
        assert del_resp.status_code == 204
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "user_deleted" for e in entries)

    def test_role_changed_logged(self, auth_client, db):
        """Changing a user's role via admin endpoint logs role_changed event."""
        admin = auth_client("admin")
        resp = admin.post("/api/admin/users", json={
            "username": "rolechange_audit", "email": "rolechange@example.com",
            "password": "Str0ng-Audit-Pw!", "display_name": "Role Change", "role": "tester"
        })
        assert resp.status_code == 201
        user_id = resp.json()["id"]
        patch_resp = admin.patch(f"/api/admin/users/{user_id}/role", json={"role": "manager"})
        assert patch_resp.status_code == 200
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "role_changed" for e in entries)


# ---------------------------------------------------------------------------
# AUDIT-03: Test and run events
# ---------------------------------------------------------------------------

class TestTestRunEvents:
    def test_test_created_logged(self, auth_client):
        """Creating a test logs test_created event."""
        mgr = auth_client("manager")
        resp = mgr.post("/api/tests", json={"title": "Audit Test Case", "status": "pending"})
        assert resp.status_code == 201
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "test_created" for e in entries)

    def test_test_updated_logged(self, auth_client):
        """Updating a test logs test_updated event."""
        mgr = auth_client("manager")
        resp = mgr.post("/api/tests", json={"title": "Update Audit Test", "status": "pending"})
        assert resp.status_code == 201
        test_id = resp.json()["id"]
        patch_resp = mgr.patch(f"/api/tests/{test_id}", json={"title": "Updated Title"})
        assert patch_resp.status_code == 200
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "test_updated" for e in entries)

    def test_test_deleted_logged(self, auth_client):
        """Deleting a test logs test_deleted event."""
        admin = auth_client("admin")
        resp = admin.post("/api/tests", json={"title": "Delete Audit Test", "status": "pending"})
        assert resp.status_code == 201
        test_id = resp.json()["id"]
        del_resp = admin.delete(f"/api/tests/{test_id}")
        assert del_resp.status_code == 204
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "test_deleted" for e in entries)

    def test_run_started_logged(self, auth_client):
        """Creating a run logs run_started event."""
        import uuid
        mgr = auth_client("manager")
        # Create a test first
        t_resp = mgr.post("/api/tests", json={"title": "Run Audit Test", "status": "pending"})
        test_id = t_resp.json()["id"]
        run_resp = mgr.post("/api/runs", json={
            "id": str(uuid.uuid4()), "name": "Audit Run", "status": "in_progress",
            "test_ids": [test_id]
        })
        assert run_resp.status_code == 201
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "run_started" for e in entries)

    def test_run_completed_logged(self, auth_client):
        """Marking a run as completed logs run_completed event."""
        import uuid
        mgr = auth_client("manager")
        t_resp = mgr.post("/api/tests", json={"title": "Completion Audit Test", "status": "pending"})
        test_id = t_resp.json()["id"]
        run_resp = mgr.post("/api/runs", json={
            "id": str(uuid.uuid4()), "name": "Completion Run", "status": "in_progress",
            "test_ids": [test_id]
        })
        run_id = run_resp.json()["id"]
        status_resp = mgr.patch(f"/api/runs/{run_id}/status", params={"status": "completed"})
        assert status_resp.status_code == 200
        admin = auth_client("admin")
        entries = _audit_entries(admin)
        assert any(e["event_type"] == "run_completed" for e in entries)


# ---------------------------------------------------------------------------
# AUDIT-04: Role guards on GET /api/audit-log
# ---------------------------------------------------------------------------

class TestAuditLogEndpoint:
    def test_admin_can_access(self, auth_client):
        """Admin role can GET /api/audit-log."""
        admin = auth_client("admin")
        resp = admin.get("/api/audit-log")
        assert resp.status_code == 200

    def test_manager_can_access(self, auth_client):
        """Manager role can GET /api/audit-log."""
        mgr = auth_client("manager")
        resp = mgr.get("/api/audit-log")
        assert resp.status_code == 200

    def test_tester_cannot_access(self, auth_client):
        """Tester role gets 403 on GET /api/audit-log."""
        tester = auth_client("tester")
        resp = tester.get("/api/audit-log")
        assert resp.status_code == 403

    def test_viewer_cannot_access(self, auth_client):
        """Viewer role gets 403 on GET /api/audit-log."""
        viewer = auth_client("viewer")
        resp = viewer.get("/api/audit-log")
        assert resp.status_code == 403

    def test_response_shape(self, auth_client):
        """Response has entries, total, page, page_size keys."""
        admin = auth_client("admin")
        resp = admin.get("/api/audit-log")
        assert resp.status_code == 200
        body = resp.json()
        assert "entries" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body

    # ---------------------------------------------------------------------------
    # AUDIT-05: Date-range filter
    # ---------------------------------------------------------------------------

    def test_date_filter(self, auth_client):
        """Date-range filter returns only entries within the specified window."""
        admin = auth_client("admin")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Filter to today only
        resp = admin.get("/api/audit-log", params={"start_date": today, "end_date": today})
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        # All returned entries must have occurred_at >= today
        for entry in entries:
            assert entry["occurred_at"][:10] >= today, f"Entry date {entry['occurred_at']} outside filter"

    def test_date_filter_excludes_old_entries(self, auth_client, db):
        """Entries outside date range are excluded."""
        from backend import models
        from backend.db import SessionLocal
        admin = auth_client("admin")
        # Manually insert an old entry
        audit_db = SessionLocal()
        old_entry = models.AuditLog(
            event_type="login_success",
            actor_email="old@example.com",
            description="old entry",
            outcome="success",
            occurred_at="2020-01-01T00:00:00Z",
        )
        audit_db.add(old_entry)
        audit_db.commit()
        audit_db.close()
        # Filter to today — old entry should not appear
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        resp = admin.get("/api/audit-log", params={"start_date": today, "end_date": today})
        entries = resp.json()["entries"]
        assert not any(e["occurred_at"].startswith("2020") for e in entries), "Old entry leaked through filter"
