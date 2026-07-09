"""Demo backend suite run by the GitLab pipeline's `pytest` job — all green.
The intentional failure lives in the Playwright (e2e) job instead, so the demo
shows which job/suite went red."""


def test_login_with_valid_credentials():
    assert 1 + 1 == 2


def test_promo_code_applies():
    discount = 0.10
    assert round(100 * (1 - discount), 2) == 90.00


def test_password_reset_email_sent():
    assert "sent" == "sent"
