"""Black-box security and readiness probe for a running release image.

The probe uses only public HTTP contracts plus an optional operator-supplied
admin login.  It never prints credentials or response bodies, which makes its
output safe to archive as release evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Probe:
    key: str
    ok: bool
    message: str


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    origin: str | None = None,
) -> Response:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as response:
            return Response(response.status, dict(response.headers.items()), response.read())
    except HTTPError as exc:
        return Response(exc.code, dict(exc.headers.items()), exc.read())


def _json(response: Response) -> dict[str, Any]:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _security_headers(response: Response) -> bool:
    headers = {key.lower(): value for key, value in response.headers.items()}
    csp = headers.get("content-security-policy", "")
    return (
        headers.get("x-content-type-options", "").lower() == "nosniff"
        and headers.get("referrer-policy", "").lower() == "same-origin"
        and "object-src 'none'" in csp
        and "frame-ancestors 'self'" in csp
    )


def run_probe(
    base_url: str,
    expected_version: str,
    *,
    email: str | None = None,
    password: str | None = None,
) -> list[Probe]:
    probes: list[Probe] = []

    health_response = _request(base_url, "/health")
    health = _json(health_response)
    forbidden_health_keys = {"version", "database_url", "redis_url", "secret_key"}
    probes.append(Probe(
        "liveness",
        health_response.status == 200
        and health.get("status") == "ok"
        and not forbidden_health_keys.intersection(health),
        "liveness is healthy and exposes no release/configuration details",
    ))
    probes.append(Probe(
        "security_headers",
        _security_headers(health_response),
        "CSP, nosniff, and referrer policy are active",
    ))

    ready_response = _request(base_url, "/ready")
    ready = _json(ready_response)
    probes.append(Probe(
        "readiness",
        ready_response.status == 200
        and ready.get("status") == "ready"
        and ready.get("database") == "ok"
        and ready.get("redis") == "ok"
        and ready.get("event_bus") == "ok",
        "PostgreSQL, Redis, and the event bus are ready",
    ))

    config_response = _request(base_url, "/api/config")
    config = _json(config_response)
    probes.append(Probe(
        "production_mode",
        config_response.status == 200
        and config.get("demo_mode") is False
        and config.get("demo_accounts") == [],
        "demo mode and advertised demo credentials are disabled",
    ))

    unauth = _request(
        base_url,
        "/api/tests",
        origin="https://untrusted.invalid",
    )
    unauth_headers = {key.lower(): value for key, value in unauth.headers.items()}
    probes.append(Probe(
        "anonymous_access",
        unauth.status in {401, 403},
        "protected data rejects anonymous requests",
    ))
    probes.append(Probe(
        "cors",
        unauth_headers.get("access-control-allow-origin")
        not in {"*", "https://untrusted.invalid"},
        "an untrusted origin is not allowed by CORS",
    ))

    registration = _request(
        base_url,
        "/api/auth/register",
        method="POST",
        payload={
            "username": "release-probe-user",
            "email": "release-probe@example.invalid",
            "password": "ReleaseProbePassword-2026",
            "display_name": "Release Probe",
        },
    )
    probes.append(Probe(
        "registration",
        registration.status == 403,
        "self-registration is closed",
    ))

    if email and password:
        login = _request(
            base_url,
            "/api/auth/login",
            method="POST",
            payload={"email": email, "password": password},
        )
        token = _json(login).get("access_token")
        probes.append(Probe(
            "admin_login",
            login.status == 200 and isinstance(token, str) and bool(token),
            "operator account can authenticate after bootstrap/restore",
        ))
        if token:
            traversal = _request(
                base_url,
                "/api/attachments/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
                token=token,
            )
            probes.append(Probe(
                "path_traversal",
                traversal.status in {400, 404, 422},
                "authenticated encoded attachment traversal does not return file content",
            ))
            about_response = _request(base_url, "/api/about", token=token)
            about = _json(about_response)
            releases = about.get("releases") if isinstance(about.get("releases"), list) else []
            release_versions = {
                item.get("version") for item in releases if isinstance(item, dict)
            }
            probes.append(Probe(
                "release_version",
                about_response.status == 200
                and about.get("version") == expected_version
                and expected_version in release_versions,
                f"authenticated About reports released version {expected_version}",
            ))
            tests_response = _request(base_url, "/api/tests?limit=1", token=token)
            probes.append(Probe(
                "authenticated_read",
                tests_response.status == 200,
                "authenticated API read succeeds",
            ))
    else:
        probes.append(Probe(
            "authenticated_contract",
            False,
            "operator credentials are required for the complete release probe",
        ))

    return probes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe a running ThoroTest release image")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--email", default=os.getenv("THOROTEST_PROBE_EMAIL"))
    parser.add_argument("--password-env", default="THOROTEST_PROBE_PASSWORD")
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    password = os.getenv(args.password_env)

    deadline = time.monotonic() + max(0, args.wait_seconds)
    while True:
        try:
            probes = run_probe(
                args.base_url,
                args.expected_version,
                email=args.email,
                password=password,
            )
        except (URLError, TimeoutError, ConnectionError, OSError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
            continue
        if all(probe.ok for probe in probes) or time.monotonic() >= deadline:
            break
        time.sleep(2)

    ok = all(probe.ok for probe in probes)
    if args.json:
        print(json.dumps({
            "ready": ok,
            "checks": [probe.__dict__ for probe in probes],
        }, indent=2))
    else:
        for probe in probes:
            print(f"[{'PASS' if probe.ok else 'FAIL'}] {probe.key}: {probe.message}")
        print(f"\nRelease image probe: {'READY' if ok else 'NOT READY'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
