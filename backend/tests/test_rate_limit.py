"""Bounded sliding-window rate limiting (SECURITY H-7).

The previous limiters pruned expired timestamps but never removed keys. Since
the login key is ip|email, an attacker rotating either dimension grew the dict
without bound — memory exhaustion from unauthenticated requests.
"""
import time

import pytest

from backend.rate_limit import SlidingWindowLimiter


def test_allows_up_to_limit_then_blocks():
    limiter = SlidingWindowLimiter(max_events=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.check("k")
        assert allowed
        limiter.record("k")
    allowed, retry_after = limiter.check("k")
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
    limiter = SlidingWindowLimiter(auth_router._LOGIN_MAX_FAILURES, 3600, max_keys=50)
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
