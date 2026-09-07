import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

# Make the repo root importable so `backend.*` resolves regardless of cwd.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import models  # noqa: E402

config = context.config
if config.config_file_name is not None:
    # Alembic runs inside application startup for existing releases. Preserve
    # already-created thorotest.* loggers (including runtime/readiness logs)
    # instead of disabling every logger not named in alembic.ini.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = models.Base.metadata


def _database_url() -> str:
    # Priority: -x dburl / programmatic option, then DATABASE_URL env, then
    # the app default (local SQLite).
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return os.getenv("DATABASE_URL", "sqlite:///./testhub.db")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        engine = create_engine(_database_url(), poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    else:
        context.configure(connection=connectable, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
