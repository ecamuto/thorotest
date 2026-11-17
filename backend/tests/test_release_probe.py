import io
import json
from urllib.error import HTTPError

import backend.release_probe as release_probe
from backend.release_probe import Probe, Response, _json, _security_headers


def test_security_headers_require_full_hardening_contract():
    response = Response(200, {
        "Content-Security-Policy": "default-src 'self'; object-src 'none'; frame-ancestors 'self'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
    }, b"{}")
    assert _security_headers(response)


def test_security_headers_reject_partial_policy():
    response = Response(200, {
        "Content-Security-Policy": "default-src 'self'",
        "X-Content-Type-Options": "nosniff",
    }, b"{}")
    assert not _security_headers(response)


def test_json_rejects_non_object_payloads():
    assert _json(Response(200, {}, b"[]")) == {}
    assert _json(Response(200, {}, b"not-json")) == {}


def _probe_response(_base_url, path, *, token=None, **_kwargs):
    security_headers = {
        "Content-Security-Policy": "object-src 'none'; frame-ancestors 'self'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
    }
    if path == "/health":
        return Response(200, security_headers, b'{"status":"ok"}')
    if path == "/ready":
        return Response(
            200, {}, b'{"status":"ready","database":"ok","redis":"ok","event_bus":"ok"}'
        )
    if path == "/api/config":
        return Response(200, {}, b'{"demo_mode":false,"demo_accounts":[]}')
    if path == "/api/auth/register":
        return Response(403, {}, b"{}")
    if path == "/api/auth/login":
        return Response(200, {}, b'{"access_token":"release-token"}')
    if path.startswith("/api/attachments/"):
        return Response(404, {}, b"{}")
    if path == "/api/about":
        return Response(
            200,
            {},
            b'{"version":"1.16.0","releases":[{"version":"1.16.0"}]}',
        )
    if path.startswith("/api/tests"):
        return Response(200 if token else 401, {}, b"[]")
    raise AssertionError(f"unexpected probe path: {path}")


def test_release_probe_checks_complete_authenticated_contract(monkeypatch):
    monkeypatch.setattr(release_probe, "_request", _probe_response)
    probes = release_probe.run_probe(
        "https://thorotest.example.test",
        "1.16.0",
        email="admin@example.com",
        password="secret",
    )
    assert all(probe.ok for probe in probes)
    assert {probe.key for probe in probes} == {
        "liveness",
        "security_headers",
        "readiness",
        "production_mode",
        "anonymous_access",
        "cors",
        "registration",
        "admin_login",
        "path_traversal",
        "release_version",
        "authenticated_read",
    }


def test_release_probe_requires_credentials_for_complete_contract(monkeypatch):
    monkeypatch.setattr(release_probe, "_request", _probe_response)
    probes = release_probe.run_probe("https://thorotest.example.test", "1.16.0")
    auth = next(probe for probe in probes if probe.key == "authenticated_contract")
    assert not auth.ok


def test_request_serializes_payload_and_handles_http_errors(monkeypatch):
    captured = {}

    class URLResponse:
        status = 201
        headers = {"X-Test": "ok"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def success(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return URLResponse()

    monkeypatch.setattr(release_probe, "urlopen", success)
    response = release_probe._request(
        "https://example.test/",
        "/api/tests",
        method="POST",
        payload={"name": "smoke"},
        token="token",
        origin="https://origin.test",
    )
    request = captured["request"]
    assert response.status == 201
    assert captured["timeout"] == 10
    assert request.full_url == "https://example.test/api/tests"
    assert request.method == "POST"
    assert json.loads(request.data) == {"name": "smoke"}
    assert request.headers["Authorization"] == "Bearer token"
    assert request.headers["Origin"] == "https://origin.test"

    def forbidden(_request, timeout):
        raise HTTPError(
            "https://example.test/api/tests",
            403,
            "Forbidden",
            {"X-Denied": "yes"},
            io.BytesIO(b'{"detail":"forbidden"}'),
        )

    monkeypatch.setattr(release_probe, "urlopen", forbidden)
    denied = release_probe._request("https://example.test", "/api/tests")
    assert denied.status == 403
    assert denied.headers["X-Denied"] == "yes"
    assert denied.body == b'{"detail":"forbidden"}'


def test_release_probe_main_reports_json_and_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        release_probe,
        "run_probe",
        lambda *_args, **_kwargs: [Probe("ready", True, "ready")],
    )
    assert release_probe.main([
        "--base-url", "https://example.test",
        "--expected-version", "1.16.0",
        "--json",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True

    monkeypatch.setattr(
        release_probe,
        "run_probe",
        lambda *_args, **_kwargs: [Probe("ready", False, "not ready")],
    )
    assert release_probe.main([
        "--base-url", "https://example.test",
        "--expected-version", "1.16.0",
    ]) == 1
    output = capsys.readouterr().out
    assert "[FAIL] ready: not ready" in output
    assert "Release image probe: NOT READY" in output
