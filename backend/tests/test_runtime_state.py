"""V14-0 Redis configuration, lifecycle, and integration contract."""

import asyncio
import logging
import os

import pytest

from backend.runtime_state import RedisSettings, RuntimeState


_REDIS_ENV = (
    "REDIS_URL",
    "REDIS_REQUIRED",
    "REDIS_KEY_PREFIX",
    "REDIS_CONNECT_TIMEOUT_SECONDS",
    "REDIS_SOCKET_TIMEOUT_SECONDS",
    "REDIS_JOB_TTL_SECONDS",
)


def _clear_redis_env(monkeypatch):
    for name in _REDIS_ENV:
        monkeypatch.delenv(name, raising=False)


class FakeRedis:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.closed = False

    async def ping(self):
        if self.error:
            raise self.error
        return True

    async def aclose(self):
        self.closed = True


def test_settings_default_to_optional_single_process(monkeypatch):
    _clear_redis_env(monkeypatch)
    settings = RedisSettings.from_env()
    assert settings.url is None
    assert settings.required is False
    assert settings.key_prefix == "thorotest"
    assert settings.job_ttl_seconds == 86_400


def test_settings_validate_url_prefix_and_bounds(monkeypatch):
    _clear_redis_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "https://cache.example")
    with pytest.raises(RuntimeError, match="REDIS_URL must use"):
        RedisSettings.from_env()

    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("REDIS_KEY_PREFIX", "invalid prefix")
    with pytest.raises(RuntimeError, match="REDIS_KEY_PREFIX"):
        RedisSettings.from_env()

    monkeypatch.setenv("REDIS_KEY_PREFIX", "tenant-a")
    monkeypatch.setenv("REDIS_JOB_TTL_SECONDS", "59")
    with pytest.raises(RuntimeError, match="between 60"):
        RedisSettings.from_env()


def test_settings_reject_ambiguous_required_flag(monkeypatch):
    _clear_redis_env(monkeypatch)
    monkeypatch.setenv("REDIS_REQUIRED", "treu")
    with pytest.raises(RuntimeError, match="must be a boolean"):
        RedisSettings.from_env()


def test_required_without_url_is_missing(monkeypatch):
    _clear_redis_env(monkeypatch)
    monkeypatch.setenv("REDIS_REQUIRED", "1")
    state = RuntimeState(RedisSettings.from_env())
    assert asyncio.run(state.probe()) == "missing"


def test_lifecycle_uses_one_client_and_namespaced_keys():
    fake = FakeRedis()
    calls = []

    def factory(*args, **kwargs):
        calls.append((args, kwargs))
        return fake

    settings = RedisSettings("redis://secret@cache:6379/0", True, "acme", 1.0, 1.0, 300)
    state = RuntimeState(settings, client_factory=factory)

    async def exercise():
        await state.start()
        await state.start()
        assert await state.probe() == "ok"
        assert state.key("jobs", "abc") == "acme:jobs:abc"
        await state.close()

    asyncio.run(exercise())
    assert len(calls) == 1
    assert calls[0][0][0] == settings.url
    assert fake.closed is True
    assert state.client is None


def test_probe_log_never_contains_redis_url_or_password(caplog):
    secret_url = "redis://very-secret-password@cache.internal:6379/0"
    fake = FakeRedis(RuntimeError(secret_url))
    settings = RedisSettings(secret_url, True, "thorotest", 1.0, 1.0, 300)
    state = RuntimeState(settings, client_factory=lambda *args, **kwargs: fake)

    with caplog.at_level(logging.WARNING, logger="thorotest.runtime"):
        asyncio.run(state.start())

    assert "very-secret-password" not in caplog.text
    assert secret_url not in caplog.text
    assert "RuntimeError" in caplog.text
    asyncio.run(state.close())


def test_client_initialization_error_is_sanitized(caplog):
    secret_url = "redis://another-secret@cache.internal:6379/0"
    settings = RedisSettings(secret_url, True, "thorotest", 1.0, 1.0, 300)

    def broken_factory(*args, **kwargs):
        raise ValueError(secret_url)

    state = RuntimeState(settings, client_factory=broken_factory)
    with caplog.at_level(logging.ERROR, logger="thorotest.runtime"):
        asyncio.run(state.start())

    assert state.client is None
    assert "another-secret" not in caplog.text
    assert secret_url not in caplog.text
    assert "ValueError" in caplog.text


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="TEST_REDIS_URL not configured")
def test_real_redis_round_trip():
    settings = RedisSettings(os.environ["TEST_REDIS_URL"], True, "thorotest-test", 1.0, 1.0, 60)
    state = RuntimeState(settings)

    async def exercise():
        try:
            await state.start()
            assert await state.probe() == "ok"
            assert state.client is not None
            key = state.key("v14", "round-trip")
            await state.client.set(key, "ok", ex=10)
            assert await state.client.get(key) == "ok"
            await state.client.delete(key)
        finally:
            await state.close()

    asyncio.run(exercise())
