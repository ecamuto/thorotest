from backend.release_probe import Response, _json, _security_headers


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
