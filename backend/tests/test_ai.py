import pytest
import json
from unittest.mock import AsyncMock, MagicMock
import backend.routers.ai as ai_module
from backend import models


class MockMessage:
    def __init__(self, text):
        self.content = [MagicMock(text=text)]


def make_mock_client(return_json):
    mock = MagicMock()
    mock.messages.create = AsyncMock(return_value=MockMessage(json.dumps(return_json)))
    return mock


class TestGenerateTests:
    def test_generate_returns_array(self, client, monkeypatch):
        return_data = [
            {
                "title": "Valid login",
                "steps": [{"action": "Go to login", "expected_result": "Login page shown"}],
            }
        ]
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client(return_data))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        resp = client.post("/api/ai/generate-tests", json={"description": "Login flow", "count": 2})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["steps"][0]["action"] == "Go to login"

    def test_generate_requires_auth(self, client, monkeypatch):
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client([]))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Make a request without Authorization header
        from fastapi.testclient import TestClient
        from backend.main import app
        bare_client = TestClient(app, raise_server_exceptions=False)
        resp = bare_client.post("/api/ai/generate-tests", json={"description": "test"})
        assert resp.status_code == 401


class TestSuggestEdgeCases:
    def test_suggest_returns_suggestions(self, client, db, monkeypatch):
        return_data = {
            "suggestions": [{"title": "Empty input", "rationale": "bypasses validation"}]
        }
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client(return_data))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Create a folder with a test that has steps
        folder = models.Folder(id="folder-ai-1", name="AI Test Folder", count=1)
        db.add(folder)
        db.flush()
        test = models.Test(id="TC-AI-1", title="Test AI", folder_id="folder-ai-1")
        db.add(test)
        db.flush()
        step = models.TestStep(order=1, action="Click button", expected_result="Modal opens", test_id="TC-AI-1")
        db.add(step)
        db.commit()

        resp = client.post("/api/ai/suggest-edge-cases", json={"folder_id": "folder-ai-1"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) > 0

    def test_suggest_empty_folder_422(self, client, db, monkeypatch):
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client({}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Create folder with no tests
        folder = models.Folder(id="folder-empty-1", name="Empty Folder", count=0)
        db.add(folder)
        db.commit()

        resp = client.post("/api/ai/suggest-edge-cases", json={"folder_id": "folder-empty-1"})
        assert resp.status_code == 422

    def test_suggest_null_folder_422(self, client, monkeypatch):
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client({}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        res = client.post(
            "/api/ai/suggest-edge-cases",
            json={"folder_id": None},
        )
        assert res.status_code == 422


class TestAnalyzeFlaky:
    def test_analyze_returns_diagnosis(self, client, db, monkeypatch):
        return_data = {"diagnosis": "Timing issue", "recommendations": ["Add wait"]}
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client(return_data))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Create test + run + run_case + step + step_result
        test = models.Test(id="TC-FLAKY-1", title="Flaky test")
        db.add(test)
        db.flush()

        run = models.Run(
            id="R-FLAKY-1", name="Flaky run", status="completed",
            progress=100, total=1, passed=0, failed=1, blocked=0,
            owner="tester", env="staging", branch="main"
        )
        db.add(run)
        db.flush()

        run_case = models.RunCase(run_id="R-FLAKY-1", test_id="TC-FLAKY-1", status="fail")
        db.add(run_case)
        db.flush()

        test_step = models.TestStep(order=1, action="Click", expected_result="Opens", test_id="TC-FLAKY-1")
        db.add(test_step)
        db.flush()

        step_result = models.StepResult(
            run_case_id=run_case.id,
            test_step_id=test_step.id,
            status="fail",
            actual_result="Timeout",
        )
        db.add(step_result)
        db.commit()

        resp = client.post("/api/ai/analyze-flaky", json={"test_id": "TC-FLAKY-1"})

        assert resp.status_code == 200
        data = resp.json()
        assert "diagnosis" in data

    def test_analyze_no_history_422(self, client, db, monkeypatch):
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client({}))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Create test with no run cases
        test = models.Test(id="TC-NOHISTORY-1", title="No history test")
        db.add(test)
        db.commit()

        resp = client.post("/api/ai/analyze-flaky", json={"test_id": "TC-NOHISTORY-1"})
        assert resp.status_code == 422


class TestRateLimit:
    def test_rate_limit_enforced(self, client, monkeypatch):
        import collections
        return_data = [
            {"title": "Test", "steps": [{"action": "Step 1", "expected_result": "Result"}]}
        ]
        monkeypatch.setattr(ai_module, "_ai_client", make_mock_client(return_data))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")

        # Reset rate store to ensure clean state
        monkeypatch.setattr(
            ai_module,
            "_rate_store",
            collections.defaultdict(collections.deque),
        )

        for i in range(20):
            resp = client.post("/api/ai/generate-tests", json={"description": f"Test {i}", "count": 1})
            assert resp.status_code == 200, f"Request {i+1} should succeed, got {resp.status_code}"

        resp = client.post("/api/ai/generate-tests", json={"description": "Over limit", "count": 1})
        assert resp.status_code == 429


class TestKeyConfig:
    def test_missing_key_returns_503(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(ai_module, "_ai_client", None)

        resp = client.post("/api/ai/generate-tests", json={"description": "test", "count": 1})
        assert resp.status_code == 503


class TestAIRoleGuard:
    """Regression tests: viewer-role users must receive 403 on all AI endpoints."""

    def test_viewer_cannot_generate_tests(self, auth_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")
        viewer = auth_client("viewer")
        resp = viewer.post("/api/ai/generate-tests", json={"description": "x", "count": 1})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_viewer_cannot_suggest_edge_cases(self, auth_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")
        viewer = auth_client("viewer")
        resp = viewer.post("/api/ai/suggest-edge-cases", json={"folder_id": "test-folder"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_viewer_cannot_analyze_flaky(self, auth_client, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")
        viewer = auth_client("viewer")
        resp = viewer.post("/api/ai/analyze-flaky", json={"test_id": "test-id-123"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Insufficient permissions"

    def test_tester_can_generate_tests(self, auth_client, monkeypatch):
        """Guard is not over-restrictive — tester role must still get through."""
        import backend.routers.ai as ai_module
        from unittest.mock import AsyncMock, MagicMock
        import json as json_lib
        return_data = [{"title": "T1", "steps": [{"action": "do x", "expected_result": "see y"}]}]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=MagicMock(content=[MagicMock(text=json_lib.dumps(return_data))])
        )
        monkeypatch.setattr(ai_module, "_ai_client", mock_client)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-xxx")
        tester = auth_client("tester")
        resp = tester.post("/api/ai/generate-tests", json={"description": "Login test", "count": 1})
        assert resp.status_code == 200
