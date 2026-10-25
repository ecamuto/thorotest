from backend.preflight import evaluate_environment, main


def _production_env():
    return {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "a-unique-production-secret-" + "x" * 32,
        "DATABASE_URL": "postgresql://thorotest:redacted@db/thorotest",
        "REDIS_URL": "redis://redis:6379/0",
        "REDIS_REQUIRED": "1",
        "TESTHUB_BASE_URL": "https://test.example.com",
        "ALLOWED_ORIGINS": "https://test.example.com",
        "LOG_FORMAT": "json",
        "METRICS_ENABLED": "1",
        "SMTP_HOST": "smtp.example.com",
        "CI_WORKER_ENABLED": "1",
    }


def test_production_profile_has_no_findings():
    checks = evaluate_environment(_production_env())
    assert all(check.severity == "pass" for check in checks)


def test_insecure_profile_reports_release_blockers_without_secrets():
    env = _production_env()
    secret = "do-not-print-this-secret"
    env.update({
        "ENVIRONMENT": "development",
        "SECRET_KEY": secret,
        "DATABASE_URL": "sqlite:///data.db",
        "REDIS_REQUIRED": "0",
        "TESTHUB_BASE_URL": "http://localhost:8000",
        "ALLOWED_ORIGINS": "*",
        "DEMO_MODE": "1",
        "AUTO_BOOTSTRAP": "1",
    })
    checks = evaluate_environment(env)
    assert sum(check.severity == "error" for check in checks) >= 7
    assert secret not in " ".join(check.message for check in checks)


def test_upload_extension_and_mime_overrides_must_be_paired():
    env = _production_env()
    env["UPLOAD_EXTRA_EXTENSIONS"] = ".psd"
    checks = evaluate_environment(env)
    upload = next(check for check in checks if check.key == "upload_policy")
    assert upload.severity == "error"


def test_cors_rejects_credentials_paths_and_invalid_ports():
    for origin in (
        "https://user:pass@test.example.com",
        "https://test.example.com/api",
        "https://test.example.com:bad",
    ):
        env = _production_env()
        env["ALLOWED_ORIGINS"] = origin
        cors = next(check for check in evaluate_environment(env) if check.key == "cors")
        assert cors.severity == "error"


def test_main_strict_fails_on_warning(monkeypatch, capsys):
    env = _production_env()
    env.pop("SMTP_HOST")
    monkeypatch.setattr("backend.preflight.load_dotenv", lambda: None)
    monkeypatch.setattr("backend.preflight.os.environ", env)
    assert main(["--strict", "--json"]) == 1
    assert '"ready": false' in capsys.readouterr().out
