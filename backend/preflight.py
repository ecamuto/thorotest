"""Static production-readiness gate for a commercial self-hosted install.

The command never connects to services and never prints secret values. Run it
in the same environment as the application before bootstrap/deploy::

    python -m backend.preflight --strict
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from typing import Mapping
from urllib.parse import urlparse

from dotenv import load_dotenv


_TRUE = {"1", "true", "yes", "on"}
_PLACEHOLDER_SECRET = "thorotest-dev-secret-change-in-production"


@dataclass(frozen=True)
class Check:
    key: str
    severity: str
    message: str


def _flag(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = env.get(name)
    return default if raw is None else raw.strip().lower() in _TRUE


def _add(checks: list[Check], key: str, severity: str, message: str) -> None:
    checks.append(Check(key=key, severity=severity, message=message))


def _https_origin(value: str) -> bool:
    try:
        parsed = urlparse(value)
        _ = parsed.port  # force invalid ports to raise
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in ("", "/")
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def evaluate_environment(env: Mapping[str, str]) -> list[Check]:
    """Return sanitized checks for the supplied environment mapping."""
    checks: list[Check] = []
    environment = env.get("ENVIRONMENT", env.get("ENV", "")).strip().lower()
    production = environment in {"production", "prod"}
    _add(checks, "environment", "pass" if production else "error",
         "production mode enabled" if production else "set ENVIRONMENT=production")

    secret = env.get("SECRET_KEY", "").strip()
    secret_ok = (
        len(secret) >= 32
        and secret != _PLACEHOLDER_SECRET
        and not _flag(env, "ALLOW_INSECURE_SECRET_KEY")
    )
    _add(
        checks, "secret_key", "pass" if secret_ok else "error",
        "signing key is configured" if secret_ok
        else "set a unique SECRET_KEY of at least 32 characters and disable ALLOW_INSECURE_SECRET_KEY",
    )

    database_url = env.get("DATABASE_URL", "sqlite:///./testhub.db").strip()
    postgres = urlparse(database_url).scheme in {
        "postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2",
    }
    _add(
        checks, "database", "pass" if postgres else "error",
        "PostgreSQL production database selected" if postgres
        else "commercial production profile requires PostgreSQL",
    )

    redis_url = env.get("REDIS_URL", "").strip()
    redis_ready = (
        urlparse(redis_url).scheme in {"redis", "rediss", "unix"}
        and _flag(env, "REDIS_REQUIRED")
    )
    _add(
        checks, "shared_runtime", "pass" if redis_ready else "error",
        "Redis is configured and required" if redis_ready
        else "set REDIS_URL and REDIS_REQUIRED=1",
    )

    auto_bootstrap = _flag(env, "AUTO_BOOTSTRAP")
    _add(
        checks, "migrations", "error" if auto_bootstrap else "pass",
        "workers only verify the schema" if not auto_bootstrap
        else "disable AUTO_BOOTSTRAP and run backend.bootstrap as a one-shot deployment step",
    )

    demo = _flag(env, "DEMO_MODE")
    _add(checks, "demo_mode", "error" if demo else "pass",
         "fabricated demo results disabled" if not demo else "disable DEMO_MODE")

    base_url = env.get("TESTHUB_BASE_URL", "").strip()
    https_base = _https_origin(base_url)
    _add(
        checks, "public_url", "pass" if https_base else "error",
        "public URL uses HTTPS" if https_base
        else "set TESTHUB_BASE_URL to the public https:// URL",
    )

    origins = env.get("ALLOWED_ORIGINS", base_url).strip()
    origin_values = [value.strip() for value in origins.split(",") if value.strip()]
    safe_origins = bool(origin_values) and all(_https_origin(value) for value in origin_values)
    _add(
        checks, "cors", "pass" if safe_origins else "error",
        "CORS is restricted to HTTPS origins" if safe_origins
        else "set ALLOWED_ORIGINS to explicit HTTPS origins; wildcard is not production-safe",
    )

    extra_extensions = env.get("UPLOAD_EXTRA_EXTENSIONS", "").strip()
    extra_mimes = env.get("UPLOAD_EXTRA_MIME_TYPES", "").strip()
    parsed_extensions = [value.strip() for value in extra_extensions.split(",") if value.strip()]
    parsed_mimes = [value.strip() for value in extra_mimes.split(",") if value.strip()]
    custom_upload_policy_ok = (
        bool(parsed_extensions) == bool(parsed_mimes)
        and all(value.startswith(".") for value in parsed_extensions)
        and all("/" in value and not any(c.isspace() for c in value) for value in parsed_mimes)
    )
    _add(
        checks, "upload_policy", "pass" if custom_upload_policy_ok else "error",
        "attachment extension and MIME policy is consistent" if custom_upload_policy_ok
        else "configure UPLOAD_EXTRA_EXTENSIONS and UPLOAD_EXTRA_MIME_TYPES together",
    )

    recommendations = (
        ("registration", not _flag(env, "ALLOW_OPEN_REGISTRATION"),
         "open registration disabled", "disable ALLOW_OPEN_REGISTRATION unless public signup is intentional"),
        ("logging", env.get("LOG_FORMAT", "text").strip().lower() == "json",
         "structured JSON logging enabled", "set LOG_FORMAT=json for support diagnostics"),
        ("metrics", _flag(env, "METRICS_ENABLED", True),
         "Prometheus metrics enabled", "enable METRICS_ENABLED and restrict /metrics at the ingress"),
        ("email", bool(env.get("SMTP_HOST", "").strip()),
         "system email configured", "configure SMTP for password reset and operational mail"),
        ("provider_worker", _flag(env, "CI_WORKER_ENABLED", True),
         "durable provider worker enabled", "enable CI_WORKER_ENABLED in at least one worker deployment"),
    )
    for key, ok, pass_message, warning_message in recommendations:
        _add(checks, key, "pass" if ok else "warning", pass_message if ok else warning_message)

    return checks


def _summary(checks: list[Check]) -> dict[str, int]:
    return {
        level: sum(check.severity == level for check in checks)
        for level in ("pass", "warning", "error")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a production self-hosted configuration")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="treat recommendations as release blockers")
    args = parser.parse_args(argv)

    load_dotenv()
    checks = evaluate_environment(os.environ)
    summary = _summary(checks)
    ready = summary["error"] == 0 and (not args.strict or summary["warning"] == 0)

    if args.json:
        print(json.dumps({
            "ready": ready,
            "strict": args.strict,
            "summary": summary,
            "checks": [asdict(check) for check in checks],
        }, indent=2))
    else:
        labels = {"pass": "PASS", "warning": "WARN", "error": "FAIL"}
        for check in checks:
            print(f"[{labels[check.severity]}] {check.key}: {check.message}")
        print(
            f"\n{summary['pass']} passed, {summary['warning']} warnings, "
            f"{summary['error']} errors — {'READY' if ready else 'NOT READY'}"
        )
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
