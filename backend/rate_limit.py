"""Atomic sliding-window rate limiting with optional shared Redis state.

When Redis is configured, counters are shared across workers and replicas.
Without Redis, a bounded in-process implementation keeps local development and
single-process deployments self-contained. A configured or required Redis
service never silently falls back to memory: doing so would weaken an expected
global security limit.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict, deque
from typing import Awaitable, Callable, Deque, TypeVar

import anyio

from .runtime_state import RuntimeState, runtime_state


logger = logging.getLogger("thorotest.rate_limit")
DEFAULT_MAX_KEYS = 10_000
_SCOPE_RE = re.compile(r"^[a-z0-9_-]{1,48}$")
_T = TypeVar("_T")

_SLIDING_WINDOW_SCRIPT = """
local now = redis.call('TIME')
local now_ms = (tonumber(now[1]) * 1000) + math.floor(tonumber(now[2]) / 1000)
local window_ms = tonumber(ARGV[1])
local max_events = tonumber(ARGV[2])
local cutoff = now_ms - window_ms

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
local count = redis.call('ZCARD', KEYS[1])

if count >= max_events then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest[2] then
        retry_after = math.max(
            1,
            math.ceil((tonumber(oldest[2]) + window_ms - now_ms) / 1000)
        )
    end
    redis.call('PEXPIRE', KEYS[1], window_ms)
    return {0, retry_after}
end

if ARGV[3] == '1' then
    redis.call('ZADD', KEYS[1], now_ms, ARGV[4])
    redis.call('PEXPIRE', KEYS[1], window_ms)
end

return {1, 0}
"""


class RateLimitUnavailable(RuntimeError):
    """Raised when an expected shared rate-limit backend cannot be used."""


class SlidingWindowLimiter:
    """Bounded, thread-safe in-process sliding-window limiter."""

    def __init__(
        self,
        max_events: int,
        window_seconds: int,
        max_keys: int = DEFAULT_MAX_KEYS,
    ) -> None:
        if max_events <= 0 or window_seconds <= 0 or max_keys <= 0:
            raise ValueError("rate-limit values must be positive")
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: OrderedDict[str, Deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        """Drop timestamps outside the window. Caller must hold the lock."""
        events = self._events.get(key)
        if events is None:
            return deque()
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            self._events.pop(key, None)
        return events

    def check(self, key: str) -> tuple[bool, int]:
        """Return whether an event is allowed without consuming capacity."""
        now = time.time()
        with self._lock:
            events = self._prune(key, now)
            if len(events) >= self.max_events:
                retry_after = int(self.window_seconds - (now - events[0])) + 1
                return False, max(retry_after, 1)
            if events:
                self._events.move_to_end(key)
            return True, 0

    def record(self, key: str) -> tuple[bool, int]:
        """Atomically consume capacity, or refuse when the window is full."""
        now = time.time()
        with self._lock:
            events = self._prune(key, now)
            if len(events) >= self.max_events:
                retry_after = int(self.window_seconds - (now - events[0])) + 1
                return False, max(retry_after, 1)
            if not events:
                events = deque()
                self._events[key] = events
            self._events.move_to_end(key)
            events.append(now)
            self._evict_if_needed(now)
            return True, 0

    def clear(self, key: str) -> None:
        """Forget a key, for example after a successful login."""
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        """Drop all in-process state. Intended for tests."""
        with self._lock:
            self._events.clear()

    def _evict_if_needed(self, now: float) -> None:
        """Bound tracked keys, preferring fully expired entries."""
        if len(self._events) <= self.max_keys:
            return
        cutoff = now - self.window_seconds
        for key in [
            candidate
            for candidate, events in self._events.items()
            if not events or events[-1] <= cutoff
        ]:
            del self._events[key]
        while len(self._events) > self.max_keys:
            self._events.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


def _run_async_from_sync(
    operation: Callable[..., Awaitable[_T]],
    *args: object,
) -> _T:
    """Run on FastAPI's event loop from a worker thread, or standalone."""
    try:
        anyio.from_thread.check_cancelled()
    except RuntimeError:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation(*args))
        raise RuntimeError("sync rate-limit methods cannot run on an event-loop thread")
    return anyio.from_thread.run(operation, *args)


class SharedRateLimiter:
    """Use Redis when configured, otherwise use bounded process-local state."""

    def __init__(
        self,
        scope: str,
        max_events: int,
        window_seconds: int,
        *,
        runtime: RuntimeState = runtime_state,
        max_keys: int = DEFAULT_MAX_KEYS,
        force_memory: bool = False,
    ) -> None:
        if not _SCOPE_RE.fullmatch(scope):
            raise ValueError("rate-limit scope must use lowercase letters, digits, _ or -")
        if max_events <= 0 or window_seconds <= 0:
            raise ValueError("rate-limit values must be positive")
        self.scope = scope
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.runtime = runtime
        self.force_memory = force_memory
        self._memory = SlidingWindowLimiter(max_events, window_seconds, max_keys)

    def _use_redis(self) -> bool:
        return not self.force_memory and (
            self.runtime.settings.configured or self.runtime.settings.required
        )

    def _redis_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.runtime.key("rate-limit", self.scope, digest)

    def _redis_client(self):
        client = self.runtime.client
        if client is None:
            raise RateLimitUnavailable("shared rate-limit backend is unavailable")
        return client

    async def _redis_decision(self, key: str, *, consume: bool) -> tuple[bool, int]:
        client = self._redis_client()
        try:
            result = await client.eval(
                _SLIDING_WINDOW_SCRIPT,
                1,
                self._redis_key(key),
                self.window_seconds * 1000,
                self.max_events,
                1 if consume else 0,
                uuid.uuid4().hex,
            )
            return bool(int(result[0])), int(result[1])
        except RateLimitUnavailable:
            raise
        except Exception as exc:
            logger.warning(
                "Redis rate-limit operation failed for scope %s (%s)",
                self.scope,
                type(exc).__name__,
            )
            raise RateLimitUnavailable(
                "shared rate-limit backend is unavailable"
            ) from exc

    async def check(self, key: str) -> tuple[bool, int]:
        if self._use_redis():
            return await self._redis_decision(key, consume=False)
        return self._memory.check(key)

    async def record(self, key: str) -> tuple[bool, int]:
        if self._use_redis():
            return await self._redis_decision(key, consume=True)
        return self._memory.record(key)

    async def clear(self, key: str) -> None:
        if not self._use_redis():
            self._memory.clear(key)
            return
        client = self._redis_client()
        try:
            await client.delete(self._redis_key(key))
        except Exception as exc:
            logger.warning(
                "Redis rate-limit clear failed for scope %s (%s)",
                self.scope,
                type(exc).__name__,
            )
            raise RateLimitUnavailable(
                "shared rate-limit backend is unavailable"
            ) from exc

    def check_sync(self, key: str) -> tuple[bool, int]:
        return _run_async_from_sync(self.check, key)

    def record_sync(self, key: str) -> tuple[bool, int]:
        return _run_async_from_sync(self.record, key)

    def clear_sync(self, key: str) -> None:
        _run_async_from_sync(self.clear, key)

    def reset(self) -> None:
        """Reset memory state used by tests and Redis-disabled deployments."""
        self._memory.reset()

    def __len__(self) -> int:
        return len(self._memory)
