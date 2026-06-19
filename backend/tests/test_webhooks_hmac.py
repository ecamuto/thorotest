"""
HMAC signing test coverage for the webhook infrastructure built in Phase 13-01.

Proves WBHK-01/02/03 are satisfied:
  WBHK-01 — signed run.completed delivery (X-Hub-Signature-256 header matches HMAC)
  WBHK-02 — secret shown once on creation, absent from list/get/patch
  WBHK-03 — regenerate-secret flow + 404 on unknown id
"""

import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy.orm import sessionmaker

from backend import models
from backend.webhook_utils import sign_payload
from backend.notifications import _fire_webhooks


# ---------------------------------------------------------------------------
# Task 1 — API tests: secret shown once, list/patch omit, regenerate, 404
# ---------------------------------------------------------------------------

class TestWebhookSecretLifecycle:
    """Proves WBHK-02 (shown once) and WBHK-03 (regenerate)."""

    def test_create_returns_secret_once(self, client):
        """POST /api/webhooks → 201, body contains a 64-char hex secret."""
        r = client.post("/api/webhooks", json={
            "url": "https://example.com/hook",
            "events": ["run.completed"],
        })
        assert r.status_code == 201, r.text
        data = r.json()
        assert "secret" in data, f"Expected 'secret' in response, got: {list(data.keys())}"
        secret = data["secret"]
        assert len(secret) == 64, f"Expected 64-char hex, got len={len(secret)}: {secret!r}"
        assert secret == secret.lower(), "Secret must be lowercase hex"
        assert all(c in "0123456789abcdef" for c in secret), "Secret must be hex"

    def test_list_omits_secret(self, client):
        """GET /api/webhooks → 200, no item exposes 'secret' or 'hmac_secret'."""
        # Create one first so the list is non-empty
        client.post("/api/webhooks", json={
            "url": "https://example.com/hook-list",
            "events": ["run.completed"],
        })
        r = client.get("/api/webhooks")
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        for item in items:
            assert "secret" not in item, f"'secret' must not appear in list response: {item}"
            assert "hmac_secret" not in item, f"'hmac_secret' must not appear in list response: {item}"

    def test_patch_omits_secret(self, client):
        """PATCH /api/webhooks/{id} → 200, response has no 'secret'/'hmac_secret'."""
        create_r = client.post("/api/webhooks", json={
            "url": "https://example.com/hook-patch",
            "events": ["run.completed"],
        })
        assert create_r.status_code == 201
        wh_id = create_r.json()["id"]

        r = client.patch(f"/api/webhooks/{wh_id}", json={"status": "paused"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "secret" not in data, f"'secret' must not appear in PATCH response: {data}"
        assert "hmac_secret" not in data, f"'hmac_secret' must not appear in PATCH response: {data}"

    def test_regenerate_returns_new_secret(self, client, db):
        """POST /api/webhooks/{id}/regenerate-secret → new 64-hex secret, stored in DB, differs from original."""
        create_r = client.post("/api/webhooks", json={
            "url": "https://example.com/hook-regen",
            "events": ["run.completed"],
        })
        assert create_r.status_code == 201
        original_secret = create_r.json()["secret"]
        wh_id = create_r.json()["id"]

        r = client.post(f"/api/webhooks/{wh_id}/regenerate-secret")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "secret" in data, f"Expected 'secret' in regenerate response: {list(data.keys())}"
        new_secret = data["secret"]

        # Must be a valid 64-char hex string
        assert len(new_secret) == 64, f"Expected 64-char hex, got len={len(new_secret)}"
        assert all(c in "0123456789abcdef" for c in new_secret.lower())

        # Must differ from original
        assert new_secret != original_secret, "Regenerated secret must differ from original"

        # DB must have the new value stored
        db.expire_all()
        wh = db.query(models.Webhook).filter(models.Webhook.id == wh_id).first()
        assert wh is not None
        assert wh.hmac_secret == new_secret, (
            f"DB stores {wh.hmac_secret!r}, expected {new_secret!r}"
        )

    def test_regenerate_unknown_id_404(self, client):
        """POST /api/webhooks/999999/regenerate-secret → 404 with 'Webhook not found'."""
        r = client.post("/api/webhooks/999999/regenerate-secret")
        assert r.status_code == 404, r.text
        assert r.json()["detail"] == "Webhook not found"


# ---------------------------------------------------------------------------
# Task 2 — Signing tests: run.completed, test endpoint, defensive omit
# ---------------------------------------------------------------------------

class TestWebhookSigning:
    """Proves WBHK-01 (HMAC over exact bytes delivered, header omitted when no secret)."""

    def _make_notif_session(self, db):
        """
        Return a mock SessionLocal that returns a MagicMock wrapping the test db.
        This patches backend.notifications.SessionLocal so _fire_webhooks uses
        the same in-memory DB that the test fixtures use.
        """
        mock_db = MagicMock(wraps=db)
        mock_db.close = MagicMock()  # prevent closing the test session
        return mock_db

    def test_fire_webhooks_signs_payload(self, db):
        """
        WBHK-01 core proof: _fire_webhooks sends X-Hub-Signature-256 whose value
        equals sign_payload(posted_content_bytes, hmac_secret).
        """
        known_secret = "a" * 64  # 64-char hex string

        # Seed a Run and an active Webhook with known secret
        run = models.Run(
            id="R-SIGN-1", name="Sign Test Run", status="pass",
            progress=100, total=1, passed=1, failed=0, blocked=0,
        )
        wh = models.Webhook(
            url="https://example.com/target",
            events=["run.completed"],
            status="active",
            hmac_secret=known_secret,
        )
        db.add_all([run, wh])
        db.commit()

        mock_db = self._make_notif_session(db)

        import backend.notifications as notif_mod
        with patch.object(notif_mod, "SessionLocal", return_value=mock_db):
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.post = AsyncMock(
                    return_value=AsyncMock(status_code=200)
                )
                asyncio.run(_fire_webhooks("R-SIGN-1"))

        # Verify post() was called exactly once
        assert mock_instance.post.called, "_fire_webhooks must POST to the webhook URL"
        call_kwargs = mock_instance.post.call_args.kwargs

        # Extract the body bytes that were actually sent
        assert "content" in call_kwargs, (
            f"Expected 'content=' kwarg in post() call, got: {list(call_kwargs.keys())}"
        )
        sent_body: bytes = call_kwargs["content"]
        assert isinstance(sent_body, bytes)

        # Verify the header is present and matches the locally-computed HMAC
        headers = call_kwargs.get("headers", {})
        assert "X-Hub-Signature-256" in headers, (
            f"Missing X-Hub-Signature-256 in headers: {headers}"
        )
        expected_sig = sign_payload(sent_body, known_secret)
        assert headers["X-Hub-Signature-256"] == expected_sig, (
            f"Header={headers['X-Hub-Signature-256']!r}, expected={expected_sig!r}"
        )

        # Sanity-check the body is valid JSON containing run_id and event
        body_data = json.loads(sent_body.decode("utf-8"))
        assert body_data["event"] == "run.completed"
        assert body_data["run_id"] == "R-SIGN-1"

    def test_fire_webhooks_omits_header_when_no_secret(self, db):
        """
        Defensive fallback: when hmac_secret is None, _fire_webhooks must NOT
        include an X-Hub-Signature-256 header (never an empty/invalid signature).
        """
        run = models.Run(
            id="R-NOSEC-1", name="No Secret Run", status="pass",
            progress=100, total=1, passed=1, failed=0, blocked=0,
        )
        wh = models.Webhook(
            url="https://example.com/unsigned",
            events=["run.completed"],
            status="active",
            hmac_secret=None,
        )
        db.add_all([run, wh])
        db.commit()

        mock_db = self._make_notif_session(db)

        import backend.notifications as notif_mod
        with patch.object(notif_mod, "SessionLocal", return_value=mock_db):
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.post = AsyncMock(
                    return_value=AsyncMock(status_code=200)
                )
                asyncio.run(_fire_webhooks("R-NOSEC-1"))

        assert mock_instance.post.called, "_fire_webhooks must POST when webhook is active"
        call_kwargs = mock_instance.post.call_args.kwargs
        headers = call_kwargs.get("headers", {})
        assert "X-Hub-Signature-256" not in headers, (
            f"X-Hub-Signature-256 must be absent when no secret, got headers: {headers}"
        )

    def test_fire_webhooks_skips_inactive_or_unsubscribed(self, db):
        """
        Inactive webhooks (status != 'active') and webhooks not subscribed to
        'run.completed' must NOT receive delivery.
        """
        run = models.Run(
            id="R-SKIP-1", name="Skip Test Run", status="pass",
            progress=100, total=1, passed=1, failed=0, blocked=0,
        )
        # Paused webhook — should be skipped
        wh_paused = models.Webhook(
            url="https://example.com/paused",
            events=["run.completed"],
            status="paused",
            hmac_secret="b" * 64,
        )
        # Wrong event — should be skipped
        wh_other = models.Webhook(
            url="https://example.com/other",
            events=["build.failed"],
            status="active",
            hmac_secret="c" * 64,
        )
        db.add_all([run, wh_paused, wh_other])
        db.commit()

        mock_db = self._make_notif_session(db)

        import backend.notifications as notif_mod
        with patch.object(notif_mod, "SessionLocal", return_value=mock_db):
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_instance.post = AsyncMock(
                    return_value=AsyncMock(status_code=200)
                )
                asyncio.run(_fire_webhooks("R-SKIP-1"))

        assert not mock_instance.post.called, (
            "post() must NOT be called for paused or wrong-event webhooks"
        )

    def test_test_endpoint_signs_when_secret_set(self, client):
        """
        POST /api/webhooks/{id}/test sends X-Hub-Signature-256 starting with 'sha256='
        when the webhook has a secret.
        """
        # Create a webhook via the HTTP API — it will have a generated secret
        create_r = client.post("/api/webhooks", json={
            "url": "https://example.com/test-hook",
            "events": ["test"],
        })
        assert create_r.status_code == 201
        wh_id = create_r.json()["id"]

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock(
                return_value=AsyncMock(status_code=200)
            )
            r = client.post(f"/api/webhooks/{wh_id}/test")

        assert r.status_code == 200, r.text

        # The test endpoint must have called httpx.AsyncClient.post
        assert mock_instance.post.called, "Test endpoint must POST to webhook URL"
        call_kwargs = mock_instance.post.call_args.kwargs
        headers = call_kwargs.get("headers", {})
        assert "X-Hub-Signature-256" in headers, (
            f"X-Hub-Signature-256 missing from test-endpoint POST headers: {headers}"
        )
        sig = headers["X-Hub-Signature-256"]
        assert sig.startswith("sha256="), (
            f"Signature must start with 'sha256=', got: {sig!r}"
        )
        # Verify it's a full HMAC (sha256= + 64 hex chars)
        assert len(sig) == len("sha256=") + 64, (
            f"Expected sha256=<64-hex>, got len={len(sig)}: {sig!r}"
        )
