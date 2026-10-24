"""V14-2 cross-worker event delivery contract."""

import asyncio
import json
import os
import uuid

import pytest

from backend.event_bus import RuntimeEventBus
from backend.notifications import NotificationManager
from backend.runtime_state import RedisSettings, RuntimeState
from backend.ws_manager import RunWSManager


class FakeRedis:
    def __init__(self):
        self.published = []

    async def publish(self, channel, message):
        self.published.append((channel, message))
        return 1


class _BrokenPubSub:
    async def subscribe(self, channel):
        raise ConnectionError("simulated disconnect")

    async def aclose(self):
        return None


class _HealthyPubSub:
    async def subscribe(self, channel):
        return None

    async def get_message(self, timeout=1.0):
        await asyncio.sleep(0.01)
        return None

    async def aclose(self):
        return None


class _ReconnectRedis:
    def __init__(self):
        self.calls = 0

    def pubsub(self, **kwargs):
        self.calls += 1
        return _BrokenPubSub() if self.calls == 1 else _HealthyPubSub()


class FakeEventBus:
    def __init__(self):
        self.handlers = {}
        self.published = []

    def register(self, event_type, handler):
        self.handlers[event_type] = handler

    async def publish(self, event_type, payload):
        self.published.append((event_type, payload))
        return True


class FakeWebSocket:
    def __init__(self):
        self.messages = []

    async def accept(self):
        return None

    async def send_json(self, payload):
        self.messages.append(payload)


class BrokenWebSocket(FakeWebSocket):
    async def send_json(self, payload):
        raise RuntimeError("socket closed")


def test_publish_wraps_version_origin_and_namespaced_channel():
    settings = RedisSettings("redis://cache:6379/0", True, "acme", 1, 1, 60)
    runtime = RuntimeState(settings)
    runtime._client = FakeRedis()
    bus = RuntimeEventBus(runtime)

    assert asyncio.run(bus.publish("run", {"run_id": "R-1"})) is True
    channel, raw = runtime.client.published[0]
    body = json.loads(raw)
    assert channel == "acme:events:v1"
    assert body["version"] == 1
    assert body["origin"] == bus.origin
    assert body["type"] == "run"
    assert body["payload"] == {"run_id": "R-1"}


def test_dispatch_ignores_origin_and_delivers_remote_event_once():
    runtime = RuntimeState(
        RedisSettings(None, False, "test", 1, 1, 60)
    )
    bus = RuntimeEventBus(runtime)
    received = []

    async def handler(payload):
        received.append(payload)

    bus.register("notification", handler)

    async def exercise():
        await bus._dispatch({
            "version": 1,
            "origin": bus.origin,
            "type": "notification",
            "payload": {"id": 1},
        })
        await bus._dispatch({
            "version": 1,
            "origin": "other-worker",
            "type": "notification",
            "payload": {"id": 2},
        })

    asyncio.run(exercise())
    assert received == [{"id": 2}]


def test_bus_readiness_requires_subscription_only_when_redis_is_enabled():
    disabled = RuntimeEventBus(
        RuntimeState(RedisSettings(None, False, "test", 1, 1, 60))
    )
    enabled = RuntimeEventBus(
        RuntimeState(
            RedisSettings("redis://cache:6379/0", True, "test", 1, 1, 60)
        )
    )

    assert disabled.ready is True
    assert enabled.ready is False
    enabled._ready.set()
    assert enabled.ready is True


def test_subscriber_reconnects_and_becomes_ready_after_disconnect():
    runtime = RuntimeState(
        RedisSettings("redis://cache:6379/0", True, "test", 1, 1, 60)
    )
    runtime._client = _ReconnectRedis()
    bus = RuntimeEventBus(runtime)

    async def exercise():
        await bus.start()
        try:
            await bus.wait_until_ready(timeout=2)
        finally:
            await bus.close()

    asyncio.run(exercise())
    assert runtime.client.calls >= 2
    assert bus.reconnects == 1


def test_run_manager_delivers_locally_then_publishes_for_other_workers():
    bus = FakeEventBus()
    manager = RunWSManager(event_bus=bus)
    socket = FakeWebSocket()

    async def exercise():
        await manager.connect("R-1", socket)
        await manager.broadcast("R-1", {"event": "step"})
        await bus.handlers["run"]({
            "run_id": "R-1", "message": {"event": "complete"}
        })

    asyncio.run(exercise())
    assert socket.messages == [{"event": "step"}, {"event": "complete"}]
    assert bus.published == [
        ("run", {"run_id": "R-1", "message": {"event": "step"}})
    ]


def test_run_manager_prunes_dead_local_socket():
    bus = FakeEventBus()
    manager = RunWSManager(event_bus=bus)
    socket = BrokenWebSocket()

    async def exercise():
        await manager.connect("R-dead", socket)
        await manager.broadcast("R-dead", {"event": "step"})

    asyncio.run(exercise())
    assert "R-dead" not in manager.connections


def test_notification_manager_delivers_locally_then_publishes():
    bus = FakeEventBus()
    manager = NotificationManager(event_bus=bus)
    socket = FakeWebSocket()

    async def exercise():
        await manager.connect(7, socket)
        await manager.push(7, {"id": 1})
        await bus.handlers["notification"]({
            "user_id": 7, "message": {"id": 2}
        })

    asyncio.run(exercise())
    assert socket.messages == [{"id": 1}, {"id": 2}]
    assert bus.published == [
        ("notification", {"user_id": 7, "message": {"id": 1}})
    ]


@pytest.mark.skipif(
    not os.getenv("TEST_REDIS_URL"), reason="TEST_REDIS_URL is not configured"
)
def test_real_redis_delivers_between_two_worker_instances():
    """Prove the actual Pub/Sub path, not only the in-process fake contract."""
    prefix = f"thorotest-test-{uuid.uuid4().hex}"
    settings = RedisSettings(
        os.environ["TEST_REDIS_URL"], True, prefix, 1, 1, 60
    )
    runtime_a = RuntimeState(settings)
    runtime_b = RuntimeState(settings)
    bus_a = RuntimeEventBus(runtime_a)
    bus_b = RuntimeEventBus(runtime_b)
    received = []
    delivered = asyncio.Event()

    async def receive(payload):
        received.append(payload)
        delivered.set()

    bus_b.register("run", receive)

    async def exercise():
        await runtime_a.start()
        await runtime_b.start()
        await bus_a.start()
        await bus_b.start()
        try:
            await asyncio.gather(
                bus_a.wait_until_ready(), bus_b.wait_until_ready()
            )
            assert await bus_a.publish("run", {"run_id": "R-redis"}) is True
            await asyncio.wait_for(delivered.wait(), timeout=3)
        finally:
            await bus_a.close()
            await bus_b.close()
            await runtime_a.close()
            await runtime_b.close()

    asyncio.run(exercise())
    assert received == [{"run_id": "R-redis"}]
