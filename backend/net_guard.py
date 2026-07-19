"""Shared SSRF egress guard for user/admin-supplied outbound URLs (SECURITY
M-1 / roadmap S-8): webhooks, GitLab self-hosted api_base, Jira base_url.

`assert_public_http_url` rejects a URL whose host resolves to a private,
loopback, link-local, reserved, or otherwise non-public address — the classic
SSRF pivots (cloud metadata at 169.254.169.254, localhost services, RFC-1918
internal hosts). It resolves the hostname and checks *every* returned address,
so a public name that resolves to an internal IP (DNS-rebinding style) is also
blocked.

Set NET_GUARD_ALLOW_PRIVATE_HOSTS=1 (or the legacy WEBHOOK_ALLOW_PRIVATE_HOSTS)
to disable the IP checks — needed for local dev and the e2e suite, which point
webhooks and a local GitLab at 127.0.0.1. Never set either in production.

Deliberately NOT guarded: AI_BASE_URL. It is operator-set environment config
(never writable through the API), and pointing it at a private host is the
supported local-LLM setup (Ollama, LM Studio, vLLM).
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to call (bad scheme or non-public host)."""


def _guard_disabled() -> bool:
    for var in ("NET_GUARD_ALLOW_PRIVATE_HOSTS", "WEBHOOK_ALLOW_PRIVATE_HOSTS"):
        if os.getenv(var, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def _ip_is_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # unparseable — refuse
    # IPv4-mapped IPv6 (::ffff:a.b.c.d) — unwrap to judge the real target.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_http_url(url: str, *, resolve: bool = True) -> None:
    """Raise UnsafeURLError unless `url` is an http(s) URL on a public host.
    A no-op when NET_GUARD_ALLOW_PRIVATE_HOSTS is set.

    With resolve=False only the scheme and literal-IP hosts are judged — no
    DNS lookup. Use it for save-time validation (fail fast without a network
    dependency); the outbound clients re-check with full resolution at use
    time, which also covers hostnames that point at internal addresses.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("URL must use http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    if _guard_disabled():
        return

    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        raise UnsafeURLError("host localhost is not allowed")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # hostname, not a literal IP
    else:
        if _ip_is_blocked(host):
            raise UnsafeURLError(f"host {host} is a non-public address")

    if not resolve:
        return

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise UnsafeURLError(f"cannot resolve host: {host}")
    if not infos:
        raise UnsafeURLError(f"cannot resolve host: {host}")
    for info in infos:
        ip = info[4][0]
        if _ip_is_blocked(ip):
            raise UnsafeURLError(f"host {host} resolves to a non-public address ({ip})")
