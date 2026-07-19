import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./testhub.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite is the eval/small-install default; production should run Postgres
# (single-writer contention under live runs + imports + sync). Warn, don't
# refuse — small single-team prod installs on SQLite are still legitimate.
if _is_sqlite and os.getenv("ENVIRONMENT", os.getenv("ENV", "")).strip().lower() in ("production", "prod"):
    import logging
    logging.getLogger("thorotest.db").warning(
        "Running SQLite in production: one writer at a time. PostgreSQL is the "
        "recommended production database — see docs/configuration.md."
    )
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
_engine_kwargs = {"pool_pre_ping": True} if not _is_sqlite else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
