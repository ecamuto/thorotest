"""Shared-runtime configuration and Redis lifecycle.

V14-0 only establishes the connection contract. Rate limits, cross-worker
WebSocket delivery, and CI job state are migrated in subsequent milestones.
Keeping the lifecycle in one module prevents each feature from opening its own
pool and gives readiness checks one authoritative view of Redis availability.
"""

from __future__ import annotations

import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from redis.asyncio import Redis


logger = logging.getLogger("thorotest.runtime")
_KEY_PREFIX_RE = re.compile(r"^[A-Za-z0-9:_-]{1,64}$")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise RuntimeError(f"{name} must be a boolean (1/0, true/false, yes/no, on/off)")


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class RedisSettings:
    """Validated Redis settings, safe to expose without the connection URL."""

    url: str | None
    required: bool
    key_prefix: str
    socket_connect_timeout: float
    socket_timeout: float
    job_ttl_seconds: int

    @property
    def configured(self) -> bool:
        return self.url is not None

    @classmethod
    def from_env(cls) -> "RedisSettings":
        raw_url = os.getenv("REDIS_URL", "").strip()
        url = raw_url or None
        if url:
            # Validate only the scheme. Host/socket validation belongs to the
            # Redis client, and errors must never echo a credential-bearing URL.
            if urlparse(url).scheme not in {"redis", "rediss", "unix"}:
                raise RuntimeError("REDIS_URL must use redis://, rediss://, or unix://")

        key_prefix = os.getenv("REDIS_KEY_PREFIX", "thorotest").strip().rstrip(":")
        if not key_prefix or not _KEY_PREFIX_RE.fullmatch(key_prefix):
            raise RuntimeError(
                "REDIS_KEY_PREFIX must be 1-64 letters, digits, colon, underscore, or hyphen"
            )

        return cls(
            url=url,
            required=_env_flag("REDIS_REQUIRED"),
            key_prefix=key_prefix,
            socket_connect_timeout=_positive_float("REDIS_CONNECT_TIMEOUT_SECONDS", 2.0),
            socket_timeout=_positive_float("REDIS_SOCKET_TIMEOUT_SECONDS", 2.0),
            job_ttl_seconds=_bounded_int("REDIS_JOB_TTL_SECONDS", 86_400, 60, 2_592_000),
        )


RedisFactory = Callable[..., Redis]


class RuntimeState:
    """Own the process-wide async Redis client and readiness probe."""

    def __init__(
        self,
        settings: RedisSettings | None = None,
        client_factory: RedisFactory = Redis.from_url,
    ) -> None:
        self.settings = settings or RedisSettings.from_env()
        self._client_factory = client_factory
        self._client: Redis | None = None
        self._started = False

    @property
    def client(self) -> Redis | None:
        """Return the shared client, or None when Redis is not configured."""
        return self._client

    def key(self, *parts: object) -> str:
        """Build an installation-namespaced Redis key."""
        suffix = ":".join(str(part).strip(":") for part in parts)
        return f"{self.settings.key_prefix}:{suffix}" if suffix else self.settings.key_prefix

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        if not self.settings.configured:
            if self.settings.required:
                logger.error("Redis is required but REDIS_URL is not configured")
            else:
                logger.info("Redis is disabled; using single-process runtime state")
            return

        # from_url is lazy and does no network I/O. Keep the client even when
        # the first ping fails so readiness can observe a later recovery.
        try:
            self._client = self._client_factory(
                self.settings.url,
                decode_responses=True,
                socket_connect_timeout=self.settings.socket_connect_timeout,
                socket_timeout=self.settings.socket_timeout,
                health_check_interval=30,
            )
        except Exception as exc:
            # A malformed client option must not leak the credential-bearing
            # URL through an exception raised during application startup.
            logger.error("Redis client initialization failed (%s)", type(exc).__name__)
            return
        status = await self.probe(log_failure=True)
        if status == "ok":
            logger.info("Redis runtime state connected")

    async def probe(self, *, log_failure: bool = False) -> str:
        """Return ok, disabled, missing, or unreachable without exposing config."""
        if not self.settings.configured:
            return "missing" if self.settings.required else "disabled"
        if self._client is None:
            return "unreachable"
        try:
            await self._client.ping()
            return "ok"
        except Exception as exc:
            if log_failure:
                # Log only the exception type. Some client messages include the
                # Redis address, which can contain credentials.
                logger.warning("Redis readiness probe failed (%s)", type(exc).__name__)
            return "unreachable"

    async def close(self) -> None:
        client, self._client = self._client, None
        self._started = False
        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                logger.warning("Redis client close failed (%s)", type(exc).__name__)


runtime_state = RuntimeState()
