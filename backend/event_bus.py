"""Cross-worker logical event delivery over the shared Redis connection.

WebSocket objects remain local to each worker.  Producers deliver to their
local sockets immediately, then publish a small logical event here so every
other worker can deliver the same payload to its own local sockets.  The
origin identifier prevents the publishing worker from delivering twice.

Redis-free development intentionally keeps the old single-process behaviour.
When Redis is configured but temporarily unavailable, local delivery still
works and readiness removes the process from traffic; failures are observable
through logs and the metrics counters exposed by :mod:`backend.observability`.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from .runtime_state import RuntimeState, runtime_state
from .observability import redis_failure, redis_reconnect


logger = logging.getLogger("thorotest.event_bus")
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class RuntimeEventBus:
    """Redis Pub/Sub event bus with explicit lifecycle and reconnects."""

    def __init__(self, runtime: RuntimeState = runtime_state) -> None:
        self.runtime = runtime
        self.origin = uuid.uuid4().hex
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self.publish_failures = 0
        self.reconnects = 0

    @property
    def enabled(self) -> bool:
        return self.runtime.settings.configured

    @property
    def ready(self) -> bool:
        """Whether cross-worker delivery is disabled or actively subscribed."""
        return not self.enabled or self._ready.is_set()

    @property
    def channel(self) -> str:
        return self.runtime.key("events", "v1")

    def register(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop.clear()
        self._ready.clear()
        self._task = asyncio.create_task(
            self._listen(), name="thorotest-redis-events"
        )

    async def close(self) -> None:
        self._stop.set()
        self._ready.clear()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def wait_until_ready(self, timeout: float = 5.0) -> None:
        """Wait until this worker has subscribed, primarily for startup gates/tests."""
        if not self.enabled:
            return
        await asyncio.wait_for(self._ready.wait(), timeout=timeout)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> bool:
        """Publish an event for other workers; return whether Redis accepted it."""
        if not self.enabled:
            return False
        client = self.runtime.client
        if client is None:
            self.publish_failures += 1
            redis_failure("event_publish")
            logger.warning("Redis event publish skipped: runtime client unavailable")
            return False
        envelope = json.dumps(
            {
                "version": 1,
                "id": uuid.uuid4().hex,
                "origin": self.origin,
                "type": event_type,
                "payload": payload,
            },
            separators=(",", ":"),
        )
        try:
            await client.publish(self.channel, envelope)
            return True
        except Exception as exc:
            self.publish_failures += 1
            redis_failure("event_publish")
            logger.warning("Redis event publish failed (%s)", type(exc).__name__)
            return False

    async def _dispatch(self, envelope: dict[str, Any]) -> None:
        if envelope.get("version") != 1 or envelope.get("origin") == self.origin:
            return
        event_type = envelope.get("type")
        payload = envelope.get("payload")
        if not isinstance(event_type, str) or not isinstance(payload, dict):
            logger.warning("Ignoring malformed Redis event")
            return
        for handler in tuple(self._handlers.get(event_type, ())):
            try:
                result = handler(payload)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning(
                    "Redis event handler failed for %s (%s)",
                    event_type,
                    type(exc).__name__,
                )

    async def _listen(self) -> None:
        backoff = 0.25
        while not self._stop.is_set():
            pubsub = None
            try:
                client = self.runtime.client
                if client is None:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                pubsub = client.pubsub(ignore_subscribe_messages=True)
                await pubsub.subscribe(self.channel)
                self._ready.set()
                backoff = 0.25
                while not self._stop.is_set():
                    message = await pubsub.get_message(timeout=1.0)
                    if not message:
                        continue
                    raw = message.get("data")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        envelope = json.loads(raw)
                    except (TypeError, json.JSONDecodeError):
                        logger.warning("Ignoring malformed Redis event JSON")
                        continue
                    if isinstance(envelope, dict):
                        await self._dispatch(envelope)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._ready.clear()
                self.reconnects += 1
                redis_reconnect()
                redis_failure("event_subscribe")
                logger.warning(
                    "Redis event subscriber disconnected (%s); reconnecting",
                    type(exc).__name__,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 5.0)
            finally:
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass


runtime_event_bus = RuntimeEventBus()
