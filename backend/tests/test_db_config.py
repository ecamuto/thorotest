from backend.db import normalize_database_url


def test_documented_postgres_url_selects_installed_driver():
    assert normalize_database_url(
        "postgresql://user:secret@db:5432/thorotest"
    ) == "postgresql+psycopg2://user:secret@db:5432/thorotest"


def test_legacy_postgres_alias_is_supported():
    assert normalize_database_url(
        "postgres://user:secret@db:5432/thorotest"
    ) == "postgresql+psycopg2://user:secret@db:5432/thorotest"


def test_explicit_driver_and_sqlite_urls_are_unchanged():
    assert normalize_database_url("postgresql+psycopg://db/app") == (
        "postgresql+psycopg://db/app"
    )
    assert normalize_database_url("sqlite:///./testhub.db") == (
        "sqlite:///./testhub.db"
    )
