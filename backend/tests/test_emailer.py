from backend import emailer


class _SMTP:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.calls = []
        self.message = None
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self, **kwargs):
        self.calls.append(("starttls", kwargs))

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, message):
        self.message = message


def test_emailer_reports_configuration_and_drops_without_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert not emailer.is_configured()
    assert not emailer.send_email("qa@example.com", "Subject", "Body")

    monkeypatch.setenv("SMTP_HOST", " smtp.example.com ")
    assert emailer.is_configured()


def test_emailer_uses_starttls_auth_and_user_as_default_sender(monkeypatch):
    _SMTP.instances.clear()
    context = object()
    monkeypatch.setattr(emailer.smtplib, "SMTP", _SMTP)
    monkeypatch.setattr(emailer.ssl, "create_default_context", lambda: context)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setenv("SMTP_STARTTLS", "yes")

    assert emailer.send_email("qa@example.com", "Subject", "Body")
    smtp = _SMTP.instances[-1]
    assert (smtp.host, smtp.port, smtp.kwargs["timeout"]) == (
        "smtp.example.com", 587, 15,
    )
    assert smtp.calls == [
        ("starttls", {"context": context}),
        ("login", "sender@example.com", "secret"),
    ]
    assert smtp.message["From"] == "sender@example.com"
    assert smtp.message["To"] == "qa@example.com"
    assert smtp.message.get_content().strip() == "Body"


def test_emailer_supports_implicit_tls_without_auth(monkeypatch):
    _SMTP.instances.clear()
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", _SMTP)
    monkeypatch.setattr(emailer.ssl, "create_default_context", lambda: "tls-context")
    monkeypatch.setenv("SMTP_HOST", "secure.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")

    assert emailer.send_email("qa@example.com", "TLS", "Secure")
    smtp = _SMTP.instances[-1]
    assert smtp.kwargs == {"context": "tls-context", "timeout": 15}
    assert smtp.calls == []
    assert smtp.message["From"] == "noreply@example.com"


def test_emailer_returns_false_when_relay_fails(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("relay unavailable")

    monkeypatch.setattr(emailer.smtplib, "SMTP", fail)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "25")
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.delenv("SMTP_FROM", raising=False)

    assert not emailer.send_email("qa@example.com", "Failure", "Body")
