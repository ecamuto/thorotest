"""Bounded in-process sliding-window rate limiting.

Replaces three near-identical `defaultdict(deque)` counters (login, AI, 2FA)
that pruned expired timestamps but never removed keys. Because the login key is
``ip|email``, an attacker rotating either dimension grew the dict without bound
— a memory-exhaustion DoS reachable with unauthenticated requests (SECURITY
H-7). This module bounds the key count and drops keys once their window empties.

**This is per-process.** With more than one uvicorn worker or replica, each
holds its own counters, so the effective limit is N times the configured one.
That is a real limitation, not an oversight: shared limits need Redis, which is
item S-1 on the roadmap. Deployments that need an enforced global limit should
run a single worker or put a rate limiter in front of the app.
"""
import threading
import time
from collections import OrderedDict, deque
from typing import Deque, Tuple

# Ceiling on tracked keys per limiter. Well above any realistic number of
# concurrent legitimate clients, low enough that the worst case is bounded.
DEFAULT_MAX_KEYS = 10_000


class SlidingWindowLimiter:
    """Counts events per key within a moving time window.

    Thread-safe. Uses a threading lock rather than an asyncio one so the same
    instance works from sync handlers, async handlers, and background threads;
    every critical section is a few dict operations.
    """

    def __init__(self, max_events: int, window_seconds: int, max_keys: int = DEFAULT_MAX_KEYS):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        # OrderedDict as an LRU: least-recently-touched key is evicted first.
        self._events: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        """Drop timestamps outside the window. Caller must hold the lock."""
        dq = self._events.get(key)
        if dq is None:
            return deque()
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()
        if not dq:
            # Nothing left in the window — forget the key entirely rather than
            # leaving an empty deque behind. This is the actual leak fix.
            self._events.pop(key, None)
        return dq

    def check(self, key: str) -> Tuple[bool, int]:
        """Return (allowed, retry_after_seconds) without recording anything."""
        now = time.time()
        with self._lock:
            dq = self._prune(key, now)
            if len(dq) >= self.max_events:
                retry_after = int(self.window_seconds - (now - dq[0])) + 1
                return False, max(retry_after, 1)
            return True, 0

    def record(self, key: str) -> None:
        """Count one event against `key`."""
        now = time.time()
        with self._lock:
            dq = self._events.get(key)
            if dq is None:
                dq = deque()
                self._events[key] = dq
            self._events.move_to_end(key)
            dq.append(now)
            self._evict_if_needed(now)

    def clear(self, key: str) -> None:
        """Forget a key — e.g. after a successful login."""
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        """Drop all state. For tests."""
        with self._lock:
            self._events.clear()

    def _evict_if_needed(self, now: float) -> None:
        """Bound the key count. Caller must hold the lock.

        Sweeps fully-expired keys first (they cost nothing to drop and are the
        common case under key-rotation abuse); only if that is not enough does
        it evict live entries in least-recently-used order.
        """
        if len(self._events) <= self.max_keys:
            return
        cutoff = now - self.window_seconds
        for key in [k for k, dq in self._events.items() if not dq or dq[-1] < cutoff]:
            del self._events[key]
        while len(self._events) > self.max_keys:
            self._events.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)
