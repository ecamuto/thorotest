"""Run simulation must be inert unless DEMO_MODE is explicitly enabled.

The simulator fabricates run results (random pass/fail/blocked), so in a
normal (non-demo) deployment start_simulation must be a no-op — real runs
get their results from manual case updates, step results, or imports.
"""
import asyncio

import backend.ws_manager as ws_manager


def test_start_simulation_noop_without_demo_mode(monkeypatch):
    monkeypatch.setattr(ws_manager, "DEMO_MODE", False)
    mgr = ws_manager.RunWSManager()

    asyncio.run(mgr.start_simulation("R-999"))

    assert mgr.running_tasks == {}


def test_start_simulation_runs_with_demo_mode(monkeypatch):
    monkeypatch.setattr(ws_manager, "DEMO_MODE", True)
    mgr = ws_manager.RunWSManager()

    started = []

    async def fake_simulate(run_id):
        started.append(run_id)
        mgr.running_tasks.pop(run_id, None)

    monkeypatch.setattr(mgr, "_simulate", fake_simulate)

    async def scenario():
        await mgr.start_simulation("R-999")
        # Let the created task run to completion
        await asyncio.gather(*[t for t in [mgr.running_tasks.get("R-999")] if t])

    asyncio.run(scenario())

    assert started == ["R-999"]
    assert mgr.running_tasks == {}


def test_demo_mode_env_parsing(monkeypatch):
    import importlib

    for raw, expected in [("1", True), ("true", True), ("YES", True), ("", False), ("0", False), ("off", False)]:
        monkeypatch.setenv("DEMO_MODE", raw)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        mod = importlib.reload(ws_manager)
        assert mod.DEMO_MODE is expected, f"DEMO_MODE={raw!r}"

    # Restore module state for other tests
    monkeypatch.delenv("DEMO_MODE", raising=False)
    importlib.reload(ws_manager)


# ── /api/config — public UI bootstrap flags ─────────────────────

def test_config_demo_mode_off_by_default(client, monkeypatch):
    monkeypatch.setattr(ws_manager, "DEMO_MODE", False)
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"demo_mode": False}


def test_config_demo_mode_on(client, monkeypatch):
    monkeypatch.setattr(ws_manager, "DEMO_MODE", True)
    assert client.get("/api/config").json() == {"demo_mode": True}


def test_config_is_public_and_minimal(db, monkeypatch):
    """No auth required (login screen needs it), and nothing but the flag."""
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend.db import get_db

    monkeypatch.setattr(ws_manager, "DEMO_MODE", True)

    def override():
        yield db
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        r = c.get("/api/config")
    app.dependency_overrides.clear()
    assert r.status_code == 200
    assert set(r.json().keys()) == {"demo_mode"}
