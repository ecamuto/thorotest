"""SSRF egress guard for user/admin-supplied outbound URLs (webhooks, etc.).

`assert_public_http_url` rejects a URL whose host resolves to a private,
loopback, link-local, reserved, or otherwise non-public address — the classic
SSRF pivots (cloud metadata at 169.254.169.254, localhost services, RFC-1918
internal hosts). It resolves the hostname and checks *every* returned address,
so a public name that resolves to an internal IP (DNS-rebinding style) is also
blocked.

Set WEBHOOK_ALLOW_PRIVATE_HOSTS=1 to disable the IP checks — needed for local
dev and the e2e suite, which point webhooks at 127.0.0.1. Never set it in
production.
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to call (bad scheme or non-public host)."""


def _guard_disabled() -> bool:
    return os.getenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", "").strip().lower() in ("1", "true", "yes")


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


def assert_public_http_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is an http(s) URL whose host resolves
    only to public addresses. A no-op when WEBHOOK_ALLOW_PRIVATE_HOSTS is set."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("URL must use http or https")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    if _guard_disabled():
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
