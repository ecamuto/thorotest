"""Tests for Test Detail tab endpoints — Fase 4 (History, Defects, Comments)."""
from backend import models


class TestRunHistory:
    """GET /api/tests/{test_id}/history"""

    def test_returns_200(self, seeded, client):
        r = client.get("/api/tests/TC-A1/history")
        assert r.status_code == 200

    def test_returns_list(self, seeded, client):
        r = client.get("/api/tests/TC-A1/history")
        assert isinstance(r.json(), list)

    def test_test_in_run_appears_in_history(self, seeded, client):
        # TC-A1 is in R-TEST
        history = client.get("/api/tests/TC-A1/history").json()
        run_ids = [h["run_id"] for h in history]
        assert "R-TEST" in run_ids

    def test_history_entry_has_required_fields(self, seeded, client):
        history = client.get("/api/tests/TC-A1/history").json()
        assert len(history) > 0
        entry = history[0]
        for field in ("run_id", "run_name", "case_status", "env", "branch"):
            assert field in entry, f"history entry missing field: {field}"

    def test_case_status_correct(self, seeded, client):
        history = client.get("/api/tests/TC-A1/history").json()
        entry = next(h for h in history if h["run_id"] == "R-TEST")
        assert entry["case_status"] == "pass"

    def test_fail_case_status_correct(self, seeded, client):
        history = client.get("/api/tests/TC-C2/history").json()
        entry = next(h for h in history if h["run_id"] == "R-TEST")
        assert entry["case_status"] == "fail"

    def test_test_not_in_any_run_returns_empty(self, seeded, client):
        # TC-C3 is not in R-TEST
        history = client.get("/api/tests/TC-C3/history").json()
        assert history == []


class TestTestDefects:
    """GET /api/tests/{test_id}/defects and POST /api/defects"""

    def test_list_returns_200(self, seeded, client):
        r = client.get("/api/tests/TC-A1/defects")
        assert r.status_code == 200

    def test_list_returns_empty_when_none(self, seeded, client):
        r = client.get("/api/tests/TC-A1/defects")
        assert r.json() == []  # seeded defects have no test_id

    def test_list_returns_defects_for_test(self, seeded, client, db):
        db.add(models.Defect(id="BUG-99", title="Linked defect", status="open",
                             severity="high", test_id="TC-A1"))
        db.commit()
        r = client.get("/api/tests/TC-A1/defects")
        data = r.json()
        assert len(data) == 1
        assert data[0]["id"] == "BUG-99"

    def test_defect_has_required_fields(self, seeded, client, db):
        db.add(models.Defect(id="BUG-88", title="Field check", status="open",
                             severity="critical", test_id="TC-C1"))
        db.commit()
        d = client.get("/api/tests/TC-C1/defects").json()[0]
        for field in ("id", "title", "status", "severity"):
            assert field in d, f"defect missing field: {field}"

    def test_only_returns_defects_for_requested_test(self, seeded, client, db):
        db.add(models.Defect(id="BUG-77", title="Other test bug", status="open",
                             severity="low", test_id="TC-A2"))
        db.add(models.Defect(id="BUG-76", title="This test bug", status="open",
                             severity="high", test_id="TC-C2"))
        db.commit()
        r = client.get("/api/tests/TC-C2/defects")
        ids = [d["id"] for d in r.json()]
        assert "BUG-76" in ids
        assert "BUG-77" not in ids


class TestCreateDefect:
    """POST /api/defects"""

    def test_creates_defect_and_returns_201(self, seeded, client):
        r = client.post("/api/defects", json={
            "title": "New bug", "severity": "high",
            "test_id": "TC-A1", "run_id": "R-TEST",
        })
        assert r.status_code == 201

    def test_created_defect_has_open_status(self, seeded, client):
        r = client.post("/api/defects", json={
            "title": "Auto-open bug", "severity": "med",
        })
        assert r.json()["status"] == "open"

    def test_created_defect_has_correct_fields(self, seeded, client):
        r = client.post("/api/defects", json={
            "title": "Critical issue", "severity": "critical",
            "test_id": "TC-C1",
        })
        d = r.json()
        assert d["title"] == "Critical issue"
        assert d["severity"] == "critical"
        assert d["test_id"] == "TC-C1"

    def test_created_defect_id_format(self, seeded, client):
        r = client.post("/api/defects", json={"title": "ID format test", "severity": "low"})
        bug_id = r.json()["id"]
        assert bug_id.startswith("BUG-")
        assert len(bug_id) == 8  # "BUG-" + 4 digits

    def test_created_defect_appears_in_test_defects(self, seeded, client):
        client.post("/api/defects", json={
            "title": "Linked to TC-A2", "severity": "high", "test_id": "TC-A2",
        })
        defects = client.get("/api/tests/TC-A2/defects").json()
        titles = [d["title"] for d in defects]
        assert "Linked to TC-A2" in titles


class TestComments:
    """GET and POST /api/tests/{test_id}/comments"""

    def test_list_returns_200(self, seeded, client):
        r = client.get("/api/tests/TC-A1/comments")
        assert r.status_code == 200

    def test_list_returns_empty_initially(self, seeded, client):
        r = client.get("/api/tests/TC-A1/comments")
        assert r.json() == []

    def test_add_comment_returns_201(self, seeded, client):
        r = client.post("/api/tests/TC-A1/comments", json={
            "who": "marco", "text": "Looks good to me",
        })
        assert r.status_code == 201

    def test_added_comment_has_correct_fields(self, seeded, client):
        r = client.post("/api/tests/TC-A1/comments", json={
            "who": "alice", "text": "Needs review",
        })
        c = r.json()
        assert c["who"] == "alice"
        assert c["text"] == "Needs review"
        assert c["test_id"] == "TC-A1"
        assert "when" in c

    def test_comment_has_id(self, seeded, client):
        r = client.post("/api/tests/TC-A1/comments", json={
            "who": "bob", "text": "LGTM",
        })
        assert "id" in r.json()

    def test_comment_appears_in_list(self, seeded, client):
        client.post("/api/tests/TC-C1/comments", json={
            "who": "marco", "text": "Flaky on CI",
        })
        comments = client.get("/api/tests/TC-C1/comments").json()
        texts = [c["text"] for c in comments]
        assert "Flaky on CI" in texts

    def test_multiple_comments_returned(self, seeded, client):
        client.post("/api/tests/TC-A2/comments", json={"who": "a", "text": "First"})
        client.post("/api/tests/TC-A2/comments", json={"who": "b", "text": "Second"})
        comments = client.get("/api/tests/TC-A2/comments").json()
        assert len(comments) == 2

    def test_comments_scoped_to_test(self, seeded, client):
        client.post("/api/tests/TC-C2/comments", json={"who": "x", "text": "Only for C2"})
        # TC-C3 should still have none
        other = client.get("/api/tests/TC-C3/comments").json()
        assert other == []

    def test_add_comment_to_nonexistent_test_returns_404(self, client):
        r = client.post("/api/tests/TC-GHOST/comments", json={
            "who": "mario", "text": "This test doesn't exist",
        })
        assert r.status_code == 404

    def test_default_who_uses_authenticated_user(self, seeded, client):
        """When no 'who' is provided, the authenticated user's display name is used."""
        r = client.post("/api/tests/TC-A1/comments", json={"text": "No who field"})
        assert r.json()["who"] == "Test Admin"
