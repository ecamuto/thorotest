"""Explicit Alembic bootstrap: fresh, legacy, managed, and worker checks."""
import logging
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect


@pytest.fixture
def tmp_engine(tmp_path, monkeypatch):
    """Create a throwaway SQLite target for explicit bootstrap tests."""
    url = f"sqlite:///{tmp_path}/mig.db"
    eng = create_engine(url)
    yield eng, url
    eng.dispose()


def _tables(engine):
    return set(inspect(engine).get_table_names())


def test_fresh_db_upgraded_to_head(tmp_engine):
    from backend.bootstrap import ensure_schema

    engine, url = tmp_engine
    ensure_schema(engine, url)
    tables = _tables(engine)
    assert "alembic_version" in tables
    assert {"users", "tests", "runs", "defects", "password_reset_tokens"} <= tables


def test_managed_db_is_idempotent(tmp_engine):
    from backend.bootstrap import ensure_schema

    engine, url = tmp_engine
    ensure_schema(engine, url)
    before = _tables(engine)
    ensure_schema(engine, url)
    assert _tables(engine) == before


def test_legacy_db_gets_stamped(tmp_engine, tmp_path):
    from backend.bootstrap import ensure_schema
    from backend import models

    engine, url = tmp_engine
    # Simulate a pre-Alembic install: schema via create_all, no alembic_version
    models.Base.metadata.create_all(bind=engine)
    assert "alembic_version" not in _tables(engine)

    ensure_schema(engine, url)

    assert "alembic_version" in _tables(engine)
    # Stamped at head (baseline revision present in version table)
    row = sqlite3.connect(f"{tmp_path}/mig.db").execute(
        "SELECT version_num FROM alembic_version"
    ).fetchone()
    assert row and row[0]


def test_migration_preserves_application_loggers(tmp_engine):
    from backend.bootstrap import ensure_schema

    engine, url = tmp_engine
    runtime_logger = logging.getLogger("thorotest.runtime")
    runtime_logger.disabled = False
    ensure_schema(engine, url)
    assert runtime_logger.disabled is False


def test_worker_verification_rejects_missing_and_accepts_current(tmp_engine):
    from backend.bootstrap import SchemaNotReady, ensure_schema, verify_schema

    engine, url = tmp_engine
    with pytest.raises(SchemaNotReady, match="python -m backend.bootstrap"):
        verify_schema(engine, url)

    ensure_schema(engine, url)
    verify_schema(engine, url)
