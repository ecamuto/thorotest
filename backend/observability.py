"""Structured logging, request correlation, and low-cardinality metrics."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+")
_CREDENTIAL_URL_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"
)
_PROVIDER_TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|"
    r"glpat-[A-Za-z0-9_-]{8,}|sk-(?:ant-)?[A-Za-z0-9_-]{8,})\b"
)
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:ticket|token|access_token|api_key)=)[^&\s]+"
)


HTTP_REQUESTS = Counter(
    "thorotest_http_requests_total",
    "Completed HTTP requests",
    ("method", "route", "status_class"),
)
HTTP_DURATION = Histogram(
    "thorotest_http_request_duration_seconds",
    "HTTP request duration",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_IN_FLIGHT = Gauge(
    "thorotest_http_requests_in_flight",
    "HTTP requests currently being served",
)
ACTIVE_WEBSOCKETS = Gauge(
    "thorotest_websocket_connections",
    "Active local WebSocket connections",
    ("channel",),
)
REDIS_FAILURES = Counter(
    "thorotest_redis_failures_total",
    "Redis operation or connection failures",
    ("operation",),
)
REDIS_RECONNECTS = Counter(
    "thorotest_redis_reconnects_total",
    "Redis subscriber reconnect attempts",
)
CI_JOB_OUTCOMES = Counter(
    "thorotest_ci_jobs_total",
    "Durable provider job outcomes (metric name retained for compatibility)",
    ("provider", "outcome"),
)


def redact(value: object) -> str:
    text = str(value)
    text = _JWT_RE.sub("[REDACTED_JWT]", text)
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _CREDENTIAL_URL_RE.sub(r"\1[REDACTED]@", text)
    text = _PROVIDER_TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    return _QUERY_SECRET_RE.sub(r"\1[REDACTED]", text)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        body = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "message": redact(record.getMessage()),
        }
        for field in ("method", "route", "status", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                body[field] = value
        if record.exc_info:
            body["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler())
    root.setLevel(level)
    formatter: logging.Formatter
    if os.getenv("LOG_FORMAT", "text").strip().lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s"
        )
    context_filter = RequestContextFilter()
    for handler in root.handlers:
        handler.setFormatter(formatter)
        if not any(isinstance(item, RequestContextFilter) for item in handler.filters):
            handler.addFilter(context_filter)


def resolve_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex


def route_template(request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


async def observe_http_request(request, call_next):
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    HTTP_IN_FLIGHT.inc()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration = time.perf_counter() - started
        route = route_template(request)
        status = response.status_code if response is not None else 500
        if route != "/metrics":
            HTTP_REQUESTS.labels(
                request.method, route, f"{status // 100}xx"
            ).inc()
            HTTP_DURATION.labels(request.method, route).observe(duration)
        HTTP_IN_FLIGHT.dec()
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        logging.getLogger("thorotest.request").info(
            "request complete",
            extra={
                "method": request.method,
                "route": route,
                "status": status,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        request_id_var.reset(token)


def websocket_connected(channel: str) -> None:
    ACTIVE_WEBSOCKETS.labels(channel).inc()


def websocket_disconnected(channel: str) -> None:
    ACTIVE_WEBSOCKETS.labels(channel).dec()


def redis_failure(operation: str) -> None:
    REDIS_FAILURES.labels(operation).inc()


def redis_reconnect() -> None:
    REDIS_RECONNECTS.inc()


def ci_job_outcome(provider: str, outcome: str) -> None:
    CI_JOB_OUTCOMES.labels(provider, outcome).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
