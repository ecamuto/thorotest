"""/health probe: unauthenticated, reports DB reachability.

Note: /health pings the real engine (backend.db.engine), not the per-test
in-memory session — a health check must observe the actual database.
"""
from fastapi.testclient import TestClient

from backend.main import app


def test_health_ok_without_auth():
    with TestClient(app) as c:
        r = c.get("/health")  # no Authorization header
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert isinstance(body["uptime_seconds"], int)
