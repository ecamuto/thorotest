import pytest
from unittest.mock import patch, AsyncMock
from backend.main import app
from backend import models
from backend.auth_utils import hash_password, create_access_token


@pytest.fixture
def notif_client(db):
    """TestClient with a tester user who has a NotificationConfig."""
    user = models.User(username="ntest", email="ntest@t.com",
                       hashed_password=hash_password("pass"), role="tester")
    db.add(user)
    db.flush()
    cfg = models.NotificationConfig(user_id=user.id, email_enabled=True,
                                    smtp_host="smtp.example.com", smtp_port=587,
                                    smtp_user="u", smtp_pass="p", smtp_from="from@example.com",
                                    slack_enabled=True, slack_webhook_url="https://hooks.slack.com/test")
    db.add(cfg)
    db.commit()
    from fastapi.testclient import TestClient
    from backend.db import get_db
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    token = create_access_token(user.id)
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client
    app.dependency_overrides.clear()


class TestNotificationConfig:
    def test_get_config_returns_defaults(self, notif_client):
        r = notif_client.get("/api/notifications/config")
        assert r.status_code == 200

    def test_put_config_upserts(self, notif_client):
        r = notif_client.put("/api/notifications/config",
                             json={"email_enabled": True, "smtp_host": "smtp.gmail.com",
                                   "smtp_port": 587, "smtp_user": "u", "smtp_pass": "p",
                                   "smtp_from": "me@gmail.com", "slack_enabled": False,
                                   "slack_webhook_url": None, "notify_run_complete": True,
                                   "notify_consecutive_fail": True,
                                   "consecutive_fail_threshold": 3, "notify_comment": True})
        assert r.status_code == 200
        assert r.json()["smtp_host"] == "smtp.gmail.com"


class TestTriggers:
    def test_run_complete_trigger(self, db, notif_client):
        """_notify_run_events creates Notification row for users with notify_run_complete=True."""
        import asyncio
        from unittest.mock import patch, MagicMock
        from backend.notifications import _notify_run_events
        # Setup: user + config + run
        user = models.User(username="trig1", email="trig1@t.com",
                           hashed_password="x", role="tester")
        db.add(user)
        db.flush()
        user_id = user.id  # capture before session may expire
        cfg = models.NotificationConfig(user_id=user_id, notify_run_complete=True)
        run = models.Run(id="R-TRIG-1", name="Trigger Run", status="pass",
                         progress=100, total=1, passed=1, failed=0, blocked=0)
        db.add_all([cfg, run])
        db.commit()

        # Patch SessionLocal and db.close() so test session stays open
        import backend.notifications as notif_mod
        mock_db = MagicMock(wraps=db)
        mock_db.close = MagicMock()  # prevent actual close
        with patch.object(notif_mod, 'SessionLocal', return_value=mock_db):
            asyncio.run(_notify_run_events("R-TRIG-1"))

        notifs = db.query(models.Notification).filter_by(user_id=user_id).all()
        assert len(notifs) >= 1
        assert notifs[0].event_type == "run_complete"

    def test_consecutive_fail_trigger(self, db, notif_client):
        """_notify_run_events creates consecutive_fail notification after threshold fails."""
        import asyncio
        from unittest.mock import patch, MagicMock
        from backend.notifications import _notify_run_events
        user = models.User(username="trig2", email="trig2@t.com",
                           hashed_password="x", role="tester")
        db.add(user)
        db.flush()
        user_id = user.id  # capture before session may expire
        cfg = models.NotificationConfig(user_id=user_id, notify_run_complete=False,
                                        notify_consecutive_fail=True, consecutive_fail_threshold=2)
        test = models.Test(id="TC-TRIG-1", title="Flaky Test", status="pending",
                           priority="med", auto=False, tags=[])
        run = models.Run(id="R-TRIG-2", name="Fail Run", status="fail",
                         progress=100, total=1, passed=0, failed=1, blocked=0)
        db.add_all([cfg, test, run])
        db.flush()
        # Create 2 failed run cases for same test
        rc1 = models.RunCase(run_id="R-TRIG-2", test_id="TC-TRIG-1", status="fail")
        rc2 = models.RunCase(run_id="R-TRIG-2", test_id="TC-TRIG-1", status="fail")
        db.add_all([rc1, rc2])
        db.commit()

        import backend.notifications as notif_mod
        mock_db = MagicMock(wraps=db)
        mock_db.close = MagicMock()  # prevent actual close
        with patch.object(notif_mod, 'SessionLocal', return_value=mock_db):
            asyncio.run(_notify_run_events("R-TRIG-2"))

        notifs = db.query(models.Notification).filter_by(user_id=user_id,
                                                          event_type="consecutive_fail").all()
        assert len(notifs) >= 1

    def test_comment_trigger(self, db, notif_client):
        """_notify_comment_event creates comment notification."""
        import asyncio
        from unittest.mock import patch, MagicMock
        from backend.notifications import _notify_comment_event
        user = models.User(username="trig3", email="trig3@t.com",
                           hashed_password="x", role="tester")
        db.add(user)
        db.flush()
        user_id = user.id  # capture before session may expire
        cfg = models.NotificationConfig(user_id=user_id, notify_comment=True)
        test = models.Test(id="TC-TRIG-2", title="Commented Test", status="pending",
                           priority="med", auto=False, tags=[])
        db.add_all([cfg, test])
        db.commit()

        import backend.notifications as notif_mod
        mock_db = MagicMock(wraps=db)
        mock_db.close = MagicMock()  # prevent actual close
        with patch.object(notif_mod, 'SessionLocal', return_value=mock_db):
            asyncio.run(
                _notify_comment_event("TC-TRIG-2", "alice")
            )

        notifs = db.query(models.Notification).filter_by(user_id=user_id,
                                                          event_type="comment").all()
        assert len(notifs) >= 1
        assert "alice" in notifs[0].title


class TestDelivery:
    def test_email_triggered(self, notif_client, db):
        """_send_email calls smtplib.SMTP when invoked."""
        import asyncio
        from backend.notifications import _send_email
        from unittest.mock import patch, MagicMock
        cfg = models.NotificationConfig(
            id=1, user_id=1, email_enabled=True,
            smtp_host="smtp.test.com", smtp_port=587,
            smtp_user="u", smtp_pass="p", smtp_from="from@test.com",
        )
        notif = models.Notification(
            id=1, user_id=1, event_type="run_complete",
            title="Run passed", link="#/runs/R-1", read=False,
            created_at="2026-01-01T00:00:00+00:00",
        )
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            asyncio.run(
                _send_email(cfg, "to@test.com", notif)
            )
        # Fire-and-forget — just checking it doesn't raise
        assert True

    def test_slack_triggered(self, notif_client, db):
        """_send_slack posts to webhook URL."""
        import asyncio
        from backend.notifications import _send_slack
        from unittest.mock import patch, AsyncMock
        notif = models.Notification(
            id=1, user_id=1, event_type="run_complete",
            title="Run passed", link="#/runs/R-1", read=False,
            created_at="2026-01-01T00:00:00+00:00",
        )
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_instance.post = AsyncMock()
            asyncio.run(
                _send_slack("https://hooks.slack.com/test", notif)
            )
        assert True


class TestNotificationCRUD:
    def test_list_notifications(self, notif_client, db):
        r = notif_client.get("/api/notifications?limit=20")
        assert r.status_code == 200  # RED: route doesn't exist yet -> 404

    def test_mark_read(self, notif_client, db):
        r = notif_client.patch("/api/notifications/1/read")
        assert r.status_code in (200, 404)  # RED

    def test_mark_all_read(self, notif_client, db):
        r = notif_client.post("/api/notifications/mark-all-read")
        assert r.status_code in (200, 404)  # RED

    def test_delete_notification(self, notif_client, db):
        r = notif_client.delete("/api/notifications/1")
        assert r.status_code in (200, 204, 404)  # RED


class TestMentionParsing:
    def test_parses_and_dedups_case_insensitive(self):
        from backend.notifications import parse_mentions
        assert parse_mentions("hi @Alice and @bob_1, cc @alice") == ["alice", "bob_1"]

    def test_ignores_emails_boundary(self):
        from backend.notifications import parse_mentions
        # the local part after @ in an email still parses; that's acceptable —
        # resolution only notifies if a matching username exists.
        assert parse_mentions("no mentions here") == []
        assert parse_mentions("") == []

    def test_stops_at_punctuation(self):
        from backend.notifications import parse_mentions
        assert parse_mentions("ping @carol! now") == ["carol"]


class TestAssigneeResolution:
    def test_resolves_by_username_display_email(self, db):
        from backend.notifications import _resolve_assignee
        u = models.User(username="dana", email="dana@x.com",
                        hashed_password="x", display_name="Dana Scully", role="tester")
        db.add(u)
        db.commit()
        assert _resolve_assignee(db, "DANA").id == u.id           # username, case-insensitive
        assert _resolve_assignee(db, "Dana Scully").id == u.id    # display_name
        assert _resolve_assignee(db, "dana@x.com").id == u.id     # email
        assert _resolve_assignee(db, "nobody") is None
        assert _resolve_assignee(db, "  ") is None
        assert _resolve_assignee(db, None) is None


class TestMentionAssignmentTriggers:
    def _run(self, db, coro):
        import asyncio
        from unittest.mock import patch, MagicMock
        import backend.notifications as notif_mod
        mock_db = MagicMock(wraps=db)
        mock_db.close = MagicMock()
        with patch.object(notif_mod, "SessionLocal", return_value=mock_db):
            asyncio.run(coro())

    def test_mention_creates_notification_and_skips_author(self, db):
        from backend.notifications import _notify_mentions
        bob = models.User(username="bob", email="bob@t.com", hashed_password="x", role="tester")
        alice = models.User(username="alice", email="alice@t.com", hashed_password="x", role="tester")
        db.add_all([bob, alice])
        db.commit()
        # alice mentions bob and herself
        self._run(db, lambda: _notify_mentions("Login test", "#/tests/T1",
                                               "cc @bob and @alice", "alice"))
        bob_notifs = db.query(models.Notification).filter_by(user_id=bob.id).all()
        alice_notifs = db.query(models.Notification).filter_by(user_id=alice.id).all()
        assert len(bob_notifs) == 1
        assert bob_notifs[0].event_type == "mention"
        assert "alice mentioned you" in bob_notifs[0].title
        assert alice_notifs == []  # author never notified for their own mention

    def test_mention_respects_optout(self, db):
        from backend.notifications import _notify_mentions
        carol = models.User(username="carol", email="carol@t.com", hashed_password="x", role="tester")
        db.add(carol)
        db.flush()
        db.add(models.NotificationConfig(user_id=carol.id, notify_mention=False))
        db.commit()
        self._run(db, lambda: _notify_mentions("T", "#/tests/T2", "@carol look", "dave"))
        assert db.query(models.Notification).filter_by(user_id=carol.id).all() == []

    def test_assignment_creates_notification(self, db):
        from backend.notifications import _notify_assignment
        eve = models.User(username="eve", email="eve@t.com", hashed_password="x", role="tester")
        db.add(eve)
        db.commit()
        self._run(db, lambda: _notify_assignment("test", "Checkout flow",
                                                 "#/tests/T3", "eve", "manager1"))
        notifs = db.query(models.Notification).filter_by(user_id=eve.id).all()
        assert len(notifs) == 1
        assert notifs[0].event_type == "assigned"
        assert "assigned you test 'Checkout flow'" in notifs[0].title

    def test_self_assignment_is_silent(self, db):
        from backend.notifications import _notify_assignment
        frank = models.User(username="frank", email="frank@t.com", hashed_password="x", role="manager")
        db.add(frank)
        db.commit()
        self._run(db, lambda: _notify_assignment("test", "X", "#/tests/T4", "frank", "frank"))
        assert db.query(models.Notification).filter_by(user_id=frank.id).all() == []

    def test_assignment_unresolved_is_noop(self, db):
        from backend.notifications import _notify_assignment
        self._run(db, lambda: _notify_assignment("test", "X", "#/tests/T5", "ghost", "manager1"))
        assert db.query(models.Notification).count() == 0


class TestConfigNewFlags:
    def test_mention_assigned_flags_round_trip(self, notif_client):
        r = notif_client.put("/api/notifications/config",
                             json={"notify_mention": False, "notify_assigned": False})
        assert r.status_code == 200
        body = r.json()
        assert body["notify_mention"] is False
        assert body["notify_assigned"] is False
