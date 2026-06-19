import hmac
import hashlib
import secrets


def generate_secret() -> str:
    """64-char hex signing secret (matches SQLite lower(hex(randomblob(32))))."""
    return secrets.token_hex(32)


def sign_payload(body: bytes, secret: str) -> str:
    """GitHub-style HMAC-SHA256 over the raw body bytes. Returns 'sha256=<hexdigest>'."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
