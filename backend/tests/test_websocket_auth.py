"""WebSocket endpoints require a valid session token (SECURITY H-3).

/ws/runs/{run_id} was previously unauthenticated: run IDs are guessable (and
client-supplied on POST /api/runs), so anyone could stream live run state, and
each open socket was an unreclaimed resource.
"""
import pytest

from backend import models
from backend.auth_utils import create_access_token, create_websocket_ticket, hash_password
from backend.totp_utils import create_partial_token


@pytest.fixture
def ws_user(db):
    user = models.User(
        username="wsuser", email="ws@test.com",
        hashed_password=hash_password("pass1234-long-enough"), role="tester",
    )
    db.add(user)
    db.add(models.Run(id="R-WS", name="Secret run", status="running",
                      total=1, progress=0, passed=0, failed=0, blocked=0))
    db.commit()
    db.refresh(user)
    return user


def _connect(client, url):
    """Return True if the socket opened, False if the server closed it."""
    from starlette.websockets import WebSocketDisconnect
    try:
        with client.websocket_connect(url) as ws:
            ws.receive_json()
        return True
    except WebSocketDisconnect:
        return False


@pytest.mark.parametrize("url", [
    "/ws/runs/R-WS",                    # no ticket at all
    "/ws/runs/R-WS?ticket=",            # empty ticket
    "/ws/runs/R-WS?ticket=garbage",     # unparseable ticket
])
def test_run_ws_rejects_unauthenticated(client, ws_user, url):
    assert _connect(client, url) is False


def test_run_ws_accepts_valid_ticket(client, ws_user):
    ticket = create_websocket_ticket(ws_user.id, ws_user.token_version)
    assert _connect(client, f"/ws/runs/R-WS?ticket={ticket}") is True


def test_ws_ticket_endpoint_returns_narrow_credential(client, db, ws_user):
    response = client.post("/api/auth/ws-ticket")
    assert response.status_code == 200
    data = response.json()
    assert data["expires_in"] == 60
    assert _connect(client, f"/ws/runs/R-WS?ticket={data['ticket']}") is True
    # A WS ticket must never be promoted into a REST session.
    assert client.get(
        "/api/me", headers={"Authorization": f"Bearer {data['ticket']}"}
    ).status_code == 401


def test_run_ws_rejects_full_session_token(client, ws_user):
    token = create_access_token(ws_user.id, ws_user.token_version)
    assert _connect(client, f"/ws/runs/R-WS?ticket={token}") is False


def test_partial_2fa_token_is_not_a_session_or_ws_ticket(client, ws_user):
    partial = create_partial_token(ws_user.id)
    assert client.get(
        "/api/me", headers={"Authorization": f"Bearer {partial}"}
    ).status_code == 401
    gql = client.post(
        "/graphql",
        headers={"Authorization": f"Bearer {partial}"},
        json={"query": "{ tests { id } }"},
    ).json()
    assert gql.get("data") is None
    assert gql.get("errors")
    assert _connect(client, f"/ws/runs/R-WS?ticket={partial}") is False


def test_run_ws_rejects_revoked_token(client, db, ws_user):
    """A token invalidated by logout / password reset must not open a socket
    that a REST call with the same token would reject."""
    ticket = create_websocket_ticket(ws_user.id, ws_user.token_version)
    ws_user.token_version = (ws_user.token_version or 0) + 1
    db.commit()
    assert _connect(client, f"/ws/runs/R-WS?ticket={ticket}") is False


def test_notifications_ws_rejects_revoked_token(client, db, ws_user):
    """The notifications socket decoded the JWT but skipped the token_version
    check that every other entry point performs."""
    ticket = create_websocket_ticket(ws_user.id, ws_user.token_version)
    ws_user.token_version = (ws_user.token_version or 0) + 1
    db.commit()
    from starlette.websockets import WebSocketDisconnect
    try:
        with client.websocket_connect(f"/ws/notifications?ticket={ticket}") as ws:
            ws.send_text("ping")
        opened = True
    except WebSocketDisconnect:
        opened = False
    assert opened is False


def test_api_token_cannot_open_websocket(client, ws_user):
    """API tokens are for CI and scripts — they have no reason to open a browser
    push channel, and accepting them would widen the blast radius of a leak."""
    raw = client.post("/api/tokens", json={"name": "ci", "scope": "write"}).json()["token"]
    assert _connect(client, f"/ws/runs/R-WS?ticket={raw}") is False
    assert client.post(
        "/api/auth/ws-ticket", headers={"Authorization": f"Bearer {raw}"}
    ).status_code == 403
