import json
import logging

from backend.observability import JsonFormatter, redact, resolve_request_id


def test_request_id_accepts_safe_value_and_replaces_unsafe_value():
    assert resolve_request_id("trace-123:abc") == "trace-123:abc"
    generated = resolve_request_id("bad value\nforged")
    assert generated != "bad value\nforged"
    assert len(generated) == 32


def test_log_redaction_removes_tokens_and_credential_urls():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature"
    value = redact(
        f"Authorization: Bearer secret {jwt} redis://user:password@cache/0 "
        "https://example.test/ws?ticket=secret-ticket&mode=1"
    )
    assert "password" not in value
    assert "secret-ticket" not in value
    assert jwt not in value
    assert "[REDACTED" in value


def test_json_formatter_emits_parseable_context():
    record = logging.LogRecord(
        "thorotest.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
    )
    record.request_id = "req-1"
    record.method = "GET"
    record.route = "/api/tests/{test_id}"
    record.status = 200
    record.duration_ms = 12.5
    body = json.loads(JsonFormatter().format(record))
    assert body["message"] == "hello world"
    assert body["request_id"] == "req-1"
    assert body["route"] == "/api/tests/{test_id}"
    assert body["status"] == 200


def test_request_id_header_and_metrics_endpoint(client):
    response = client.get("/health", headers={"X-Request-ID": "acceptance-42"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "acceptance-42"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
    assert "thorotest_http_requests_total" in metrics.text
    assert 'route="/health"' in metrics.text
    assert "acceptance-42" not in metrics.text


def test_metrics_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "0")
    assert client.get("/metrics").status_code == 404
