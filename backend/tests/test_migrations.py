"""Alembic schema bootstrap (_ensure_schema): fresh, legacy, and managed DBs."""
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect


@pytest.fixture
def tmp_engine(tmp_path, monkeypatch):
    """Point backend.main/_ensure_schema at a throwaway SQLite file."""
    import backend.main as main_mod
    import backend.db as db_mod

    url = f"sqlite:///{tmp_path}/mig.db"
    eng = create_engine(url)
    monkeypatch.setattr(main_mod, "engine", eng)
    monkeypatch.setattr(db_mod, "DATABASE_URL", url)
    yield eng
    eng.dispose()


def _tables(engine):
    return set(inspect(engine).get_table_names())


def test_fresh_db_upgraded_to_head(tmp_engine):
    from backend.main import _ensure_schema

    _ensure_schema()
    tables = _tables(tmp_engine)
    assert "alembic_version" in tables
    assert {"users", "tests", "runs", "defects", "password_reset_tokens"} <= tables


def test_managed_db_is_idempotent(tmp_engine):
    from backend.main import _ensure_schema

    _ensure_schema()
    before = _tables(tmp_engine)
    _ensure_schema()  # second boot: upgrade head, no-op
    assert _tables(tmp_engine) == before


def test_legacy_db_gets_stamped(tmp_engine, tmp_path):
    from backend.main import _ensure_schema
    from backend import models

    # Simulate a pre-Alembic install: schema via create_all, no alembic_version
    models.Base.metadata.create_all(bind=tmp_engine)
    assert "alembic_version" not in _tables(tmp_engine)

    _ensure_schema()

    assert "alembic_version" in _tables(tmp_engine)
    # Stamped at head (baseline revision present in version table)
    row = sqlite3.connect(f"{tmp_path}/mig.db").execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()
    assert row and row[0]
