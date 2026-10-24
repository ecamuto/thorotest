"""Explicit database migration and first-admin bootstrap command.

Run ``python -m backend.bootstrap`` once before starting application workers.
Normal workers only verify that the schema is current, so multiple replicas
never race DDL or first-user creation during a rolling deployment.
"""

from __future__ import annotations

import logging
import os
import secrets

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

from . import models
from .db import DATABASE_URL, engine


logger = logging.getLogger("thorotest.bootstrap")


class SchemaNotReady(RuntimeError):
    """Raised when a worker starts against a missing or outdated schema."""


def _alembic_config(database_url: str = DATABASE_URL) -> Config:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def _run_legacy_migrations(target_engine: Engine = engine) -> None:
    """Frozen bridge for installations created before the Alembic baseline."""
    inspector = inspect(target_engine)
    tables = inspector.get_table_names()

    with target_engine.connect() as conn:
        def add_column(
            table: str,
            column: str,
            ddl_type: str = "VARCHAR(255)",
            default: str | None = None,
        ) -> None:
            columns = [item["name"] for item in inspect(target_engine).get_columns(table)]
            if column in columns:
                return
            ddl = f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"
            if default is not None:
                ddl += f" DEFAULT {default}"
            conn.execute(text(ddl))
            conn.commit()

        if "folders" in tables:
            add_column("folders", "project_id")
        if "tests" in tables:
            add_column("tests", "project_id")
            add_column("tests", "repo_url", "VARCHAR(512)")
            add_column("tests", "source_path", "VARCHAR(512)")
            add_column("tests", "source_ref")
            add_column("tests", "source_body", "TEXT")
            add_column("tests", "source_synced_at", "VARCHAR(64)")
        if "defects" in tables:
            for column in ("description", "created_at", "created_by"):
                add_column("defects", column)
            add_column("defects", "external_provider", "VARCHAR(64)")
            add_column("defects", "external_key", "VARCHAR(128)")
            add_column("defects", "external_url", "VARCHAR(512)")
        if "users" in tables:
            add_column("users", "language", default="'en'")
            add_column("users", "totp_secret")
            add_column("users", "totp_enabled", "BOOLEAN", "FALSE")
            add_column("users", "token_version", "INTEGER", "0")
            conn.execute(text("UPDATE users SET role = 'tester' WHERE role = 'member'"))
            conn.commit()
        if "run_cases" in tables:
            add_column("run_cases", "actual_result")
            add_column("run_cases", "assigned_to")
        if "runs" in tables:
            add_column("runs", "source_run_id")
        if "integrations" in tables:
            add_column("integrations", "config", "TEXT")
        if "webhooks" in tables:
            add_column("webhooks", "hmac_secret")
            rows = conn.execute(
                text("SELECT id FROM webhooks WHERE hmac_secret IS NULL")
            ).fetchall()
            for (webhook_id,) in rows:
                conn.execute(
                    text("UPDATE webhooks SET hmac_secret = :secret WHERE id = :id"),
                    {"secret": secrets.token_hex(32), "id": webhook_id},
                )
            conn.commit()


def ensure_schema(
    target_engine: Engine = engine,
    database_url: str = DATABASE_URL,
) -> None:
    """Upgrade fresh, Alembic-managed, or legacy databases to current head."""
    cfg = _alembic_config(database_url)
    cfg.attributes["connection"] = None
    tables = inspect(target_engine).get_table_names()
    if "alembic_version" in tables or not tables:
        command.upgrade(cfg, "head")
        return

    logger.info("Pre-Alembic database detected — bridging and stamping baseline")
    models.Base.metadata.create_all(bind=target_engine)
    _run_legacy_migrations(target_engine)
    with target_engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.stamp(cfg, "head")


def expected_schema_revision(database_url: str = DATABASE_URL) -> str:
    return ScriptDirectory.from_config(_alembic_config(database_url)).get_current_head()


def current_schema_revision(target_engine: Engine = engine) -> str | None:
    if "alembic_version" not in inspect(target_engine).get_table_names():
        return None
    with target_engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def verify_schema(
    target_engine: Engine = engine,
    database_url: str = DATABASE_URL,
) -> None:
    """Fail worker startup with an actionable error when bootstrap is needed."""
    current = current_schema_revision(target_engine)
    expected = expected_schema_revision(database_url)
    if current != expected:
        found = current or "missing"
        raise SchemaNotReady(
            "Database schema is not ready "
            f"(found {found}, expected {expected}). Run `python -m backend.bootstrap` "
            "before starting application workers."
        )


def bootstrap_database() -> None:
    """Migrate schema and create the first admin, idempotently."""
    from .seed import init_db

    ensure_schema()
    init_db()
    verify_schema()
    logger.info("Database bootstrap complete at revision %s", current_schema_revision())


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bootstrap_database()
