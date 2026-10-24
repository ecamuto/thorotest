"""Bounded and shared sliding-window rate limiting (SECURITY H-7, V14-1).

The previous limiters pruned expired timestamps but never removed keys. Since
the login key is ip|email, an attacker rotating either dimension grew the dict
without bound — memory exhaustion from unauthenticated requests.
"""
import asyncio
import os
import time
import uuid

import pytest
from fastapi import HTTPException

from backend.rate_limit import (
    RateLimitUnavailable,
    SharedRateLimiter,
    SlidingWindowLimiter,
)
from backend.runtime_state import RedisSettings, RuntimeState


def test_allows_up_to_limit_then_blocks():
    limiter = SlidingWindowLimiter(max_events=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.record("k")
        assert allowed
    allowed, retry_after = limiter.record("k")
    assert not allowed
    assert retry_after > 0


def test_window_expiry_releases_the_key():
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=1)
    limiter.record("k")
    assert limiter.check("k")[0] is False
    time.sleep(1.1)
    assert limiter.check("k")[0] is True


def test_expired_keys_are_dropped_not_just_pruned():
    """The actual leak: an empty deque used to be left behind under its key."""
    limiter = SlidingWindowLimiter(max_events=5, window_seconds=1)
    for i in range(50):
        limiter.record(f"key-{i}")
    assert len(limiter) == 50

    time.sleep(1.1)
    # Checking a key prunes it; the key itself must go too.
    for i in range(50):
        limiter.check(f"key-{i}")
    assert len(limiter) == 0


def test_key_count_is_bounded_under_rotation():
    """Simulates the attack: unique key per request, far past the ceiling."""
    limiter = SlidingWindowLimiter(max_events=10, window_seconds=3600, max_keys=100)
    for i in range(5000):
        limiter.record(f"10.0.0.{i}|user{i}@example.com")
    assert len(limiter) <= 100


def test_clear_forgets_one_key_only():
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
    limiter.record("a")
    limiter.record("b")
    limiter.clear("a")
    assert limiter.check("a")[0] is True
    assert limiter.check("b")[0] is False


def test_reset_drops_everything():
    limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
    limiter.record("a")
    limiter.reset()
    assert len(limiter) == 0


def test_login_limiter_is_bounded(monkeypatch):
    """The wired-up login limiter, not just the primitive."""
    from backend.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "_LOGIN_RATELIMIT_DISABLED", False)
    limiter = SharedRateLimiter(
        "auth-test",
        auth_router._LOGIN_MAX_FAILURES,
        3600,
        max_keys=50,
        force_memory=True,
    )
    monkeypatch.setattr(auth_router, "_login_failures", limiter)

    for i in range(2000):
        auth_router._record_login_failure(auth_router._login_key(f"10.0.0.{i}", f"u{i}@x.com"))
    assert len(limiter) <= 50


def test_is_threadsafe_under_concurrent_recording():
    import threading

    limiter = SlidingWindowLimiter(max_events=10_000, window_seconds=60)

    def hammer():
        for _ in range(500):
            limiter.record("shared")

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 8 threads x 500 events, all under one key: no lost updates, no crash.
    assert len(limiter) == 1
    allowed, _ = limiter.check("shared")
    assert allowed is True


def test_concurrent_records_cannot_overspend_memory_quota():
    import threading

    limiter = SlidingWindowLimiter(max_events=100, window_seconds=60)
    decisions = []
    decisions_lock = threading.Lock()

    def hammer():
        local = [limiter.record("shared")[0] for _ in range(100)]
        with decisions_lock:
            decisions.extend(local)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(decisions) == 100


class _UnavailableLimiter:
    def check_sync(self, key):
        raise RateLimitUnavailable

    def record_sync(self, key):
        raise RateLimitUnavailable

    async def record(self, key):
        raise RateLimitUnavailable


def test_auth_rate_limit_backend_failure_returns_503(monkeypatch):
    from backend.routers import auth as auth_router

    monkeypatch.setattr(auth_router, "_LOGIN_RATELIMIT_DISABLED", False)
    monkeypatch.setattr(auth_router, "_login_failures", _UnavailableLimiter())

    with pytest.raises(HTTPException) as exc_info:
        auth_router._check_login_rate("caller")
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "5"}


def test_2fa_rate_limit_backend_failure_returns_503(monkeypatch):
    from backend import totp_utils
    from backend.routers import totp as totp_router

    monkeypatch.setattr(totp_utils, "_2fa_rate_store", _UnavailableLimiter())

    with pytest.raises(HTTPException) as exc_info:
        totp_router._check_2fa_rate_or_raise(123)
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "5"}


def test_ai_rate_limit_backend_failure_returns_503(monkeypatch):
    from backend.routers import ai as ai_router

    monkeypatch.setattr(ai_router, "_rate_store", _UnavailableLimiter())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ai_router._check_rate(123))
    assert exc_info.value.status_code == 503
    assert exc_info.value.headers == {"Retry-After": "5"}


def test_shared_limiter_hashes_caller_identifiers():
    settings = RedisSettings("redis://cache:6379/0", True, "test", 1.0, 1.0, 60)
    limiter = SharedRateLimiter(
        "auth",
        1,
        60,
        runtime=RuntimeState(settings),
    )
    redis_key = limiter._redis_key("192.0.2.1|person@example.com")
    assert "192.0.2.1" not in redis_key
    assert "person@example.com" not in redis_key
    assert redis_key.startswith("test:rate-limit:auth:")


def test_expected_redis_never_falls_back_to_memory():
    settings = RedisSettings(None, True, "test", 1.0, 1.0, 60)
    limiter = SharedRateLimiter(
        "auth",
        1,
        60,
        runtime=RuntimeState(settings),
    )
    with pytest.raises(RateLimitUnavailable):
        asyncio.run(limiter.record("caller"))
    assert len(limiter) == 0


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="TEST_REDIS_URL not configured")
def test_redis_quota_is_atomic_and_shared_across_workers():
    prefix = f"thorotest-rate-test-{uuid.uuid4().hex}"
    settings = RedisSettings(
        os.environ["TEST_REDIS_URL"],
        True,
        prefix,
        1.0,
        1.0,
        60,
    )
    first_state = RuntimeState(settings)
    second_state = RuntimeState(settings)

    async def exercise():
        try:
            await asyncio.gather(first_state.start(), second_state.start())
            first = SharedRateLimiter("auth", 5, 60, runtime=first_state)
            second = SharedRateLimiter("auth", 5, 60, runtime=second_state)

            decisions = await asyncio.gather(
                *((
                    first if index % 2 == 0 else second
                ).record("same-caller") for index in range(20))
            )
            assert sum(allowed for allowed, _ in decisions) == 5
            assert (await first.check("same-caller"))[0] is False
            assert (await second.check("same-caller"))[0] is False

            await first.clear("same-caller")
            assert (await second.check("same-caller"))[0] is True
        finally:
            await asyncio.gather(first_state.close(), second_state.close())

    asyncio.run(exercise())
