from sqlalchemy.orm import sessionmaker

from backend import models, seed


def test_demo_seed_adds_accounts_after_minimal_bootstrap_and_is_idempotent(
    db, monkeypatch
):
    sessions = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(seed, "SessionLocal", sessions)

    seed.init_db()
    seed.seed_db()
    seed.seed_db()

    check = sessions()
    try:
        emails = [
            row.email for row in check.query(models.User).order_by(models.User.email)
        ]
        assert emails.count("admin@localhost") == 1
        assert emails.count("marco@acme.com") == 1
        assert emails.count("lisa@acme.com") == 1
        assert emails.count("alex@acme.com") == 1
    finally:
        check.close()
