"""/health probe: unauthenticated, reports DB reachability.

Note: /health pings the real engine (backend.db.engine), not the per-test
in-memory session — a health check must observe the actual database.
"""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.runtime_state import runtime_state


def test_health_ok_without_auth():
    with TestClient(app) as c:
        r = c.get("/health")  # no Authorization header
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert isinstance(body["uptime_seconds"], int)


def test_health_does_not_depend_on_redis(monkeypatch):
    probe = AsyncMock(side_effect=AssertionError("/health must not probe Redis"))
    monkeypatch.setattr(runtime_state, "probe", probe)
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    probe.assert_not_awaited()


def test_readiness_accepts_intentionally_disabled_redis(monkeypatch):
    async def disabled(**kwargs):
        return "disabled"

    monkeypatch.setattr(runtime_state, "probe", disabled)
    with TestClient(app) as c:
        r = c.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["redis"] == "disabled"


def test_readiness_rejects_unreachable_configured_redis(monkeypatch):
    async def unreachable(**kwargs):
        return "unreachable"

    monkeypatch.setattr(runtime_state, "probe", unreachable)
    with TestClient(app) as c:
        r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["redis"] == "unreachable"


def test_readiness_rejects_missing_required_redis(monkeypatch):
    async def missing(**kwargs):
        return "missing"

    monkeypatch.setattr(runtime_state, "probe", missing)
    with TestClient(app) as c:
        r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["redis"] == "missing"
