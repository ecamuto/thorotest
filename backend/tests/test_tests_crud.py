"""Tests for Test CRUD endpoints — Fase 2 + Fase 5 (search/filter)."""


class TestListTests:
    def test_empty_db_returns_empty_list(self, client):
        r = client.get("/api/tests")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all_tests(self, seeded, client):
        r = client.get("/api/tests")
        assert r.status_code == 200
        assert len(r.json()) == 5

    def test_test_has_required_fields(self, seeded, client):
        tests = client.get("/api/tests").json()
        t = tests[0]
        for field in ("id", "title", "folder_id", "type", "status", "priority", "auto", "tags"):
            assert field in t, f"missing field: {field}"


class TestListTestsFilters:
    """Fase 5 — query param filters on GET /api/tests."""

    def test_filter_by_status_pass(self, seeded, client):
        r = client.get("/api/tests?status=pass")
        data = r.json()
        assert all(t["status"] == "pass" for t in data)
        assert len(data) == 3  # TC-A1, TC-A2, TC-C1

    def test_filter_by_status_fail(self, seeded, client):
        r = client.get("/api/tests?status=fail")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "TC-C2"

    def test_filter_by_status_all_returns_all(self, seeded, client):
        r = client.get("/api/tests?status=all")
        assert len(r.json()) == 5

    def test_filter_by_type_automated(self, seeded, client):
        r = client.get("/api/tests?type=automated")
        data = r.json()
        assert all(t["type"] == "automated" for t in data)
        assert len(data) == 3  # TC-A2, TC-C1, TC-C2

    def test_filter_by_type_manual(self, seeded, client):
        r = client.get("/api/tests?type=manual")
        data = r.json()
        assert all(t["type"] == "manual" for t in data)
        assert len(data) == 2  # TC-A1, TC-C3

    def test_filter_by_type_all_returns_all(self, seeded, client):
        r = client.get("/api/tests?type=all")
        assert len(r.json()) == 5

    def test_filter_by_folder_id_returns_direct_children(self, seeded, client):
        # checkout folder has TC-C1, TC-C2, TC-C3
        r = client.get("/api/tests?folder_id=checkout")
        data = r.json()
        ids = {t["id"] for t in data}
        assert ids == {"TC-C1", "TC-C2", "TC-C3"}

    def test_filter_by_folder_id_includes_child_folder_tests(self, seeded, client):
        # auth folder has no direct tests, but child auth-login has TC-A1, TC-A2
        r = client.get("/api/tests?folder_id=auth")
        data = r.json()
        ids = {t["id"] for t in data}
        assert "TC-A1" in ids
        assert "TC-A2" in ids

    def test_search_by_title_substring(self, seeded, client):
        r = client.get("/api/tests?search=cart")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "TC-C2"

    def test_search_is_case_insensitive(self, seeded, client):
        r = client.get("/api/tests?search=LOGIN")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "TC-A1"

    def test_search_no_match_returns_empty(self, seeded, client):
        r = client.get("/api/tests?search=zzznomatch")
        assert r.json() == []

    def test_combined_status_and_type_filter(self, seeded, client):
        r = client.get("/api/tests?status=pass&type=automated")
        data = r.json()
        assert all(t["status"] == "pass" and t["type"] == "automated" for t in data)
        assert len(data) == 2  # TC-A2, TC-C1


class TestGetTest:
    def test_returns_200_for_known_id(self, seeded, client):
        r = client.get("/api/tests/TC-A1")
        assert r.status_code == 200

    def test_returns_correct_test(self, seeded, client):
        t = client.get("/api/tests/TC-A1").json()
        assert t["id"] == "TC-A1"
        assert t["title"] == "Login with valid creds"
        assert t["status"] == "pass"
        assert t["type"] == "manual"

    def test_unknown_id_returns_404(self, client):
        r = client.get("/api/tests/TC-GHOST")
        assert r.status_code == 404

    def test_404_has_detail(self, client):
        r = client.get("/api/tests/TC-GHOST")
        assert "detail" in r.json()


class TestCreateTest:
    def test_creates_test_and_returns_201(self, client):
        r = client.post("/api/tests", json={
            "id": "TC-NEW", "title": "New test case", "type": "manual",
            "status": "pending", "priority": "med",
        })
        assert r.status_code == 201

    def test_created_test_has_correct_fields(self, client):
        r = client.post("/api/tests", json={
            "id": "TC-NEW2", "title": "Automated login", "type": "automated",
            "status": "pending", "priority": "high", "auto": True, "runner": "playwright",
        })
        t = r.json()
        assert t["id"] == "TC-NEW2"
        assert t["title"] == "Automated login"
        assert t["auto"] is True
        assert t["runner"] == "playwright"

    def test_duplicate_id_returns_409(self, seeded, client):
        r = client.post("/api/tests", json={
            "id": "TC-A1", "title": "Duplicate", "type": "manual",
            "status": "pending", "priority": "med",
        })
        assert r.status_code == 409

    def test_created_test_is_retrievable(self, client):
        client.post("/api/tests", json={
            "id": "TC-RETR", "title": "Retrievable", "type": "manual",
            "status": "pending", "priority": "low",
        })
        r = client.get("/api/tests/TC-RETR")
        assert r.status_code == 200
        assert r.json()["title"] == "Retrievable"

    def test_tags_stored_correctly(self, client):
        r = client.post("/api/tests", json={
            "id": "TC-TAGS", "title": "Tagged test", "type": "manual",
            "status": "pending", "priority": "med", "tags": ["smoke", "p0"],
        })
        assert r.json()["tags"] == ["smoke", "p0"]

    def test_default_status_is_pending(self, client):
        r = client.post("/api/tests", json={
            "id": "TC-DFLT", "title": "Defaults test", "type": "manual", "priority": "med",
        })
        assert r.json()["status"] == "pending"


class TestUpdateTest:
    def test_patch_status(self, seeded, client):
        r = client.patch("/api/tests/TC-A1", json={"status": "fail"})
        assert r.status_code == 200
        assert r.json()["status"] == "fail"

    def test_patch_title(self, seeded, client):
        r = client.patch("/api/tests/TC-A1", json={"title": "Updated title"})
        assert r.json()["title"] == "Updated title"

    def test_patch_priority(self, seeded, client):
        r = client.patch("/api/tests/TC-C2", json={"priority": "high"})
        assert r.json()["priority"] == "high"

    def test_patch_is_partial(self, seeded, client):
        original = client.get("/api/tests/TC-A1").json()
        client.patch("/api/tests/TC-A1", json={"status": "fail"})
        updated = client.get("/api/tests/TC-A1").json()
        assert updated["title"] == original["title"]  # unchanged
        assert updated["status"] == "fail"

    def test_patch_persists(self, seeded, client):
        client.patch("/api/tests/TC-A2", json={"status": "skip"})
        r = client.get("/api/tests/TC-A2")
        assert r.json()["status"] == "skip"

    def test_patch_unknown_returns_404(self, client):
        r = client.patch("/api/tests/TC-GHOST", json={"status": "pass"})
        assert r.status_code == 404


class TestDeleteTest:
    def test_delete_returns_204(self, seeded, client):
        r = client.delete("/api/tests/TC-A1")
        assert r.status_code == 204

    def test_deleted_test_not_retrievable(self, seeded, client):
        client.delete("/api/tests/TC-C3")
        r = client.get("/api/tests/TC-C3")
        assert r.status_code == 404

    def test_delete_unknown_returns_404(self, client):
        r = client.delete("/api/tests/TC-GHOST")
        assert r.status_code == 404

    def test_delete_removes_from_list(self, seeded, client):
        client.delete("/api/tests/TC-C1")
        ids = [t["id"] for t in client.get("/api/tests").json()]
        assert "TC-C1" not in ids


class TestBulkTests:
    def test_bulk_delete(self, seeded, client):
        r = client.post("/api/tests/bulk", json={
            "action": "delete", "ids": ["TC-A1", "TC-A2"],
        })
        assert r.status_code == 200
        assert r.json()["affected"] == 2

    def test_bulk_delete_removes_tests(self, seeded, client):
        client.post("/api/tests/bulk", json={"action": "delete", "ids": ["TC-C1", "TC-C2"]})
        remaining_ids = {t["id"] for t in client.get("/api/tests").json()}
        assert "TC-C1" not in remaining_ids
        assert "TC-C2" not in remaining_ids

    def test_bulk_update_status(self, seeded, client):
        r = client.post("/api/tests/bulk", json={
            "action": "update",
            "ids": ["TC-A1", "TC-A2"],
            "payload": {"status": "skip"},
        })
        assert r.status_code == 200
        assert r.json()["affected"] == 2

    def test_bulk_update_persists(self, seeded, client):
        client.post("/api/tests/bulk", json={
            "action": "update",
            "ids": ["TC-C1", "TC-C2", "TC-C3"],
            "payload": {"status": "blocked"},
        })
        for tid in ("TC-C1", "TC-C2", "TC-C3"):
            t = client.get(f"/api/tests/{tid}").json()
            assert t["status"] == "blocked"

    def test_bulk_with_nonexistent_ids_ignores_them(self, seeded, client):
        r = client.post("/api/tests/bulk", json={
            "action": "delete", "ids": ["TC-A1", "TC-GHOST"],
        })
        assert r.status_code == 200
        assert r.json()["affected"] == 1  # only TC-A1 existed

    def test_bulk_empty_ids_returns_zero(self, seeded, client):
        r = client.post("/api/tests/bulk", json={"action": "delete", "ids": []})
        assert r.json()["affected"] == 0
