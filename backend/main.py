import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session
from jose import JWTError, jwt as jose_jwt

# Application logging. Uvicorn configures its own access/error loggers; this
# covers the app's "thorotest.*" loggers. LOG_LEVEL env overrides (DEBUG,
# INFO, WARNING, ...). basicConfig is a no-op if the root logger is already
# configured (e.g. under pytest), so this never fights the test runner.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from sqlalchemy import event as sa_event
from .db import engine, get_db, _is_sqlite
from . import models


@sa_event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record):
    if _is_sqlite:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
from .seed import init_db, seed_db
from .ws_manager import manager
from .notifications import notif_manager
from .auth_utils import SECRET_KEY, ALGORITHM, get_current_user
from .gql_schema import graphql_router
from .routers import folders, tests, runs, pipelines, activity, auth, projects, categories, defects, requirements, integrations, tokens, webhooks, favorites, import_, attachments, admin, ai, notifications, audit_log, oauth, totp

# Serve the built frontend (frontend/dist — produced by `npm run build`).
# Fall back to the source dir so the API can still boot without a build
# (unit tests, API-only deployments); the UI itself needs the build.
_FRONTEND_SRC = os.path.join(os.path.dirname(__file__), "..", "frontend")
_FRONTEND_DIST = os.path.join(_FRONTEND_SRC, "dist")
FRONTEND_DIR = _FRONTEND_DIST if os.path.isdir(_FRONTEND_DIST) else _FRONTEND_SRC
if FRONTEND_DIR == _FRONTEND_SRC:
    import logging as _logging
    _logging.getLogger("thorotest").warning(
        "frontend/dist not found — serving unbuilt frontend sources. "
        "The UI will not render; run `npm run build` first."
    )


def _run_migrations():
    """Add new columns to existing tables without dropping data.

    Portable across SQLite / PostgreSQL / MySQL: every added column is a
    VARCHAR(255) with a dialect-neutral default, and backfills that need
    randomness are done in Python rather than with SQLite-only SQL.
    The totp_recovery_codes table is created by Base.metadata.create_all()
    (run before this function), so no manual CREATE TABLE is needed here.
    """
    import secrets

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    def _add_column(table: str, col: str, ddl_type: str = "VARCHAR(255)", default: str | None = None):
        """Add a column if missing. `default` is raw SQL (already quoted/literal)."""
        cols = [c["name"] for c in inspector.get_columns(table)]
        if col in cols:
            return
        ddl = f"ALTER TABLE {table} ADD COLUMN {col} {ddl_type}"
        if default is not None:
            ddl += f" DEFAULT {default}"
        conn.execute(text(ddl))
        conn.commit()

    with engine.connect() as conn:
        if "folders" in tables:
            _add_column("folders", "project_id")
        if "tests" in tables:
            _add_column("tests", "project_id")
        if "defects" in tables:
            for col in ("description", "created_at", "created_by"):
                _add_column("defects", col)
            # Phase 1 (v1.1): external tracker link fields (Jira in Phase 2).
            # The requirements + requirement_tests tables are created by
            # create_all() in the legacy path, so no manual CREATE TABLE needed.
            _add_column("defects", "external_provider", ddl_type="VARCHAR(64)")
            _add_column("defects", "external_key", ddl_type="VARCHAR(128)")
            _add_column("defects", "external_url", ddl_type="VARCHAR(512)")
        if "users" in tables:
            _add_column("users", "language", default="'en'")
            # Phase 2: migrate legacy "member" role to "tester"
            conn.execute(text("UPDATE users SET role = 'tester' WHERE role = 'member'"))
            conn.commit()
        if "run_cases" in tables:
            _add_column("run_cases", "actual_result")
            _add_column("run_cases", "assigned_to")
        if "runs" in tables:
            _add_column("runs", "source_run_id")

        # Tests-as-Code: git source tracking on tests + integration config blob
        if "tests" in tables:
            _add_column("tests", "repo_url", ddl_type="VARCHAR(512)")
            _add_column("tests", "source_path", ddl_type="VARCHAR(512)")
            _add_column("tests", "source_ref")
            _add_column("tests", "source_body", ddl_type="TEXT")
            _add_column("tests", "source_synced_at", ddl_type="VARCHAR(64)")
        if "integrations" in tables:
            _add_column("integrations", "config", ddl_type="TEXT")

        # v1.1 Enterprise Auth columns
        if "users" in tables:
            _add_column("users", "totp_secret")
            _add_column("users", "totp_enabled", ddl_type="BOOLEAN", default="FALSE")
            _add_column("users", "token_version", ddl_type="INTEGER", default="0")

        if "webhooks" in tables:
            _add_column("webhooks", "hmac_secret")
            # Backfill missing HMAC secrets in Python (portable across dialects)
            rows = conn.execute(text("SELECT id FROM webhooks WHERE hmac_secret IS NULL")).fetchall()
            for (wid,) in rows:
                conn.execute(
                    text("UPDATE webhooks SET hmac_secret = :s WHERE id = :id"),
                    {"s": secrets.token_hex(32), "id": wid},
                )
            conn.commit()


def _ensure_schema():
    """Bring the database schema to the current Alembic revision.

    Three cases:
    - Fresh database (no tables): `alembic upgrade head` builds the schema.
    - Pre-Alembic install (tables, no alembic_version): run the legacy
      in-place upgrades once, then stamp the baseline revision.
    - Alembic-managed: `alembic upgrade head` applies pending revisions.

    Schema changes must ship as Alembic revisions from now on — see
    "Database migrations" in README.md.
    """
    from alembic import command
    from alembic.config import Config
    from .db import DATABASE_URL

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    # % must be escaped for configparser interpolation
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))

    tables = inspect(engine).get_table_names()
    if "alembic_version" in tables or not tables:
        command.upgrade(cfg, "head")
    else:
        # Legacy pre-Alembic database: create missing tables and columns the
        # old way, then mark the DB as being at the current revision.
        logging.getLogger("thorotest").info("Pre-Alembic database detected — stamping baseline")
        models.Base.metadata.create_all(bind=engine)
        _run_migrations()
        command.stamp(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    init_db()
    yield


app = FastAPI(title="ThoroTest API", lifespan=lifespan)

# CORS origins are configurable. Default to the public base URL (same-origin
# deploys need no cross-origin access). Set ALLOWED_ORIGINS to a comma-separated
# list, or "*" to allow any origin (development only).
_origins_env = os.getenv("ALLOWED_ORIGINS", os.getenv("TESTHUB_BASE_URL", "http://localhost:8000"))
_allow_origins = ["*"] if _origins_env.strip() == "*" else [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STARTED_AT = time.monotonic()


@app.get("/health")
async def health():
    """Liveness/readiness probe: unauthenticated, checks DB connectivity.

    200 {"status":"ok"} when the app can reach the database, 503 otherwise.
    Intended for load balancers, Docker healthchecks, and uptime monitors —
    it deliberately exposes no version or configuration details.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        logging.getLogger("thorotest.health").exception("Health check DB ping failed")
        db_ok = False
    body = {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "unreachable",
        "uptime_seconds": int(time.monotonic() - _STARTED_AT),
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)

# REST
app.include_router(folders.router, prefix="/api")
app.include_router(tests.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(pipelines.router, prefix="/api")
app.include_router(activity.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(defects.router, prefix="/api")
app.include_router(requirements.router, prefix="/api")
app.include_router(integrations.router, prefix="/api")
app.include_router(tokens.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(favorites.router, prefix="/api")
app.include_router(import_.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(audit_log.router, prefix="/api")
app.include_router(oauth.router, prefix="/api")
app.include_router(totp.router, prefix="/api")

# GraphQL
app.include_router(graphql_router, prefix="/graphql")


@app.get("/api/insights")
async def insights(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    # Aggregate in SQL — this endpoint must not load whole tables into memory.
    total = db.query(func.count(models.Test.id)).scalar() or 0
    pass_count = db.query(func.count(models.Test.id)).filter(models.Test.status == "pass").scalar() or 0
    auto_count = db.query(func.count(models.Test.id)).filter(models.Test.auto == True).scalar() or 0  # noqa: E712

    _open = func.coalesce(models.Defect.status, "") != "resolved"
    open_defects = db.query(func.count(models.Defect.id)).filter(_open).scalar() or 0
    critical = db.query(func.count(models.Defect.id)).filter(_open, models.Defect.severity == "critical").scalar() or 0
    high = db.query(func.count(models.Defect.id)).filter(_open, models.Defect.severity == "high").scalar() or 0

    pass_rate = round(pass_count / total * 100, 1) if total > 0 else 0
    automation_rate = round(auto_count / total * 100) if total > 0 else 0

    # Folder coverage: folders table is small; test counts come from two
    # GROUP BY queries instead of scanning every test row in Python.
    folders = db.query(models.Folder).all()
    counts_by_folder = dict(
        db.query(models.Test.folder_id, func.count(models.Test.id))
        .group_by(models.Test.folder_id).all()
    )
    pass_by_folder = dict(
        db.query(models.Test.folder_id, func.count(models.Test.id))
        .filter(models.Test.status == "pass")
        .group_by(models.Test.folder_id).all()
    )
    folder_coverage = []
    for f in folders:
        if f.parent_id is not None:
            continue
        ids = [f.id] + [c.id for c in folders if c.parent_id == f.id]
        f_total = sum(counts_by_folder.get(i, 0) for i in ids)
        f_pass = sum(pass_by_folder.get(i, 0) for i in ids)
        folder_coverage.append({
            "name": f.name,
            "value": round(f_pass / f_total * 100) if f_total > 0 else 0,
            "mapped": f"{f_pass}/{f_total}",
        })

    all_case_counts = db.query(
        models.RunCase.test_id,
        func.count(models.RunCase.id).label("cnt"),
    ).group_by(models.RunCase.test_id).all()

    fail_case_counts = (
        db.query(models.RunCase.test_id, func.count(models.RunCase.id).label("cnt"))
        .filter(models.RunCase.status == "fail")
        .group_by(models.RunCase.test_id)
        .all()
    )
    fail_map = {r.test_id: r.cnt for r in fail_case_counts}

    candidates = [
        (row.test_id, row.cnt, fail_map[row.test_id])
        for row in all_case_counts
        if row.cnt >= 2 and fail_map.get(row.test_id, 0) > 0
    ]
    titles = {}
    if candidates:
        titles = dict(
            db.query(models.Test.id, models.Test.title)
            .filter(models.Test.id.in_([tid for tid, _, _ in candidates]))
            .all()
        )
    flaky_list = [
        {"id": tid, "title": titles[tid], "fail_rate": round(fails / cnt * 100), "total_runs": cnt}
        for tid, cnt, fails in candidates
        if tid in titles
    ]
    flaky_list.sort(key=lambda x: x["fail_rate"], reverse=True)

    return {
        "total_tests": total,
        "pass_rate": pass_rate,
        "open_defects": open_defects,
        "open_critical": critical,
        "open_high": high,
        "automation_rate": automation_rate,
        "folder_coverage": folder_coverage,
        "top_flaky": flaky_list[:5],
    }


@app.get("/api/insights/test-health")
async def test_health(days: int = 14, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Daily pass/fail/blocked/skipped totals from run result counters.

    Buckets runs by the date part of Run.created_at. Rows without created_at
    (pre-migration data) are excluded — only runs with real timestamps count.
    """
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    # created_at is a UTC ISO string, so lexicographic >= works for the cutoff.
    runs = (
        db.query(models.Run)
        .filter(models.Run.created_at.isnot(None), models.Run.created_at >= start.isoformat())
        .all()
    )
    buckets = {
        (start + timedelta(days=i)).isoformat(): {"passed": 0, "failed": 0, "blocked": 0, "skipped": 0, "runs": 0}
        for i in range(days)
    }
    for r in runs:
        day = r.created_at[:10]
        b = buckets.get(day)
        if b is None:
            continue
        passed, failed, blocked = r.passed or 0, r.failed or 0, r.blocked or 0
        b["passed"] += passed
        b["failed"] += failed
        b["blocked"] += blocked
        b["skipped"] += max((r.total or 0) - passed - failed - blocked, 0) if r.status not in ("running", "pending") else 0
        b["runs"] += 1
    day_list = [{"date": d, **v} for d, v in sorted(buckets.items())]
    return {
        "days": day_list,
        "total_runs": sum(v["runs"] for v in buckets.values()),
        "totals": {
            k: sum(v[k] for v in buckets.values())
            for k in ("passed", "failed", "blocked", "skipped")
        },
    }


# Caps for the aggregated payload below. Views that need more than this pull
# from the paginated list endpoints (which also serve server-side search).
# The `totals` key in the response carries the real row counts so the UI can
# tell when it is looking at a capped slice.
INITIAL_DATA_CAPS = {"tests": 1000, "runs": 500, "pipelines": 200, "activity": 100, "defects": 500, "requirements": 500}


# Aggregated initial-data endpoint (replaces window.TH_DATA)
@app.get("/api/initial-data")
async def initial_data(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    from .routers.folders import _build_tree

    all_folders = db.query(models.Folder).all()
    folder_tree = _build_tree(all_folders)

    totals = {
        "tests": db.query(func.count(models.Test.id)).scalar() or 0,
        "runs": db.query(func.count(models.Run.id)).scalar() or 0,
        "pipelines": db.query(func.count(models.Pipeline.id)).scalar() or 0,
        "activity": db.query(func.count(models.Activity.id)).scalar() or 0,
        "defects": db.query(func.count(models.Defect.id)).scalar() or 0,
        "requirements": db.query(func.count(models.Requirement.id)).scalar() or 0,
    }

    all_tests = db.query(models.Test).order_by(models.Test.id).limit(INITIAL_DATA_CAPS["tests"]).all()
    tests_out = [
        {
            "id": t.id, "title": t.title, "folder": t.folder_id, "type": t.type,
            "status": t.status, "priority": t.priority, "owner": t.owner,
            "updated": t.updated_at, "lastRun": t.last_run_at, "duration": t.duration,
            "tags": t.tags or [], "auto": t.auto, "runner": t.runner,
        }
        for t in all_tests
    ]

    all_runs = db.query(models.Run).order_by(models.Run.id).limit(INITIAL_DATA_CAPS["runs"]).all()
    runs_out = [
        {
            "id": r.id, "name": r.name, "status": r.status, "progress": r.progress,
            "total": r.total, "passed": r.passed, "failed": r.failed, "blocked": r.blocked,
            "started": r.started, "created_at": r.created_at,
            "owner": r.owner, "env": r.env, "branch": r.branch,
            "source_run_id": r.source_run_id,
        }
        for r in all_runs
    ]

    all_pipelines = db.query(models.Pipeline).order_by(models.Pipeline.id).limit(INITIAL_DATA_CAPS["pipelines"]).all()
    pipelines_out = [
        {
            "id": p.id, "name": p.name, "platform": p.platform, "status": p.status,
            "duration": p.duration, "commit": p.commit, "author": p.author,
            "branch": p.branch, "when": p.when,
        }
        for p in all_pipelines
    ]

    all_activity = db.query(models.Activity).order_by(models.Activity.id.desc()).limit(INITIAL_DATA_CAPS["activity"]).all()
    activity_out = [
        {"who": a.who, "what": a.what, "target": a.target, "detail": a.detail,
         "when": a.when, "created_at": a.created_at}
        for a in all_activity
    ]

    all_defects = db.query(models.Defect).order_by(models.Defect.id.desc()).limit(INITIAL_DATA_CAPS["defects"]).all()
    defects_out = [
        {"id": d.id, "title": d.title, "status": d.status, "severity": d.severity,
         "testId": d.test_id, "runId": d.run_id}
        for d in all_defects
    ]

    all_requirements = (
        db.query(models.Requirement)
        .order_by(models.Requirement.id.desc())
        .limit(INITIAL_DATA_CAPS["requirements"])
        .all()
    )
    requirements_out = []
    for r in all_requirements:
        linked = r.tests
        passed = sum(1 for t in linked if t.status == "pass")
        failed = sum(1 for t in linked if t.status == "fail")
        requirements_out.append({
            "id": r.id, "title": r.title, "type": r.type, "status": r.status,
            "priority": r.priority, "owner": r.owner,
            "externalKey": r.external_key, "externalUrl": r.external_url,
            "testIds": [t.id for t in linked],
            "coverage": {
                "linked": len(linked), "passed": passed, "failed": failed,
                "untested": len(linked) - passed - failed,
                "pass_rate": round(passed / len(linked), 4) if linked else 0.0,
            },
        })

    all_projects = db.query(models.Project).all()
    projects_out = [
        {"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at}
        for p in all_projects
    ]

    all_categories = db.query(models.Category).all()
    categories_out = [
        {"id": c.id, "name": c.name, "color": c.color}
        for c in all_categories
    ]

    return {
        "folders": [f.model_dump() for f in folder_tree],
        "tests": tests_out,
        "runs": runs_out,
        "pipelines": pipelines_out,
        "activity": activity_out,
        "defects": defects_out,
        "requirements": requirements_out,
        "projects": projects_out,
        "categories": categories_out,
        "totals": totals,
    }


# WebSocket for live run updates
@app.websocket("/ws/runs/{run_id}")
async def run_ws(run_id: str, websocket: WebSocket, db: Session = Depends(get_db)):
    await manager.connect(run_id, websocket)
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if run:
            await websocket.send_json({
                "event": "state",
                "status": run.status,
                "progress": run.progress,
                "passed": run.passed,
                "failed": run.failed,
                "blocked": run.blocked,
                "total": run.total,
            })
            if run.status == "running":
                await manager.start_simulation(run_id)

        while True:
            data = await websocket.receive_json()
            if data.get("action") == "start" and run and run.status == "running":
                await manager.start_simulation(run_id)
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)


@app.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket, token: str, db: Session = Depends(get_db)):
    """Per-user notification push channel. Token passed as query param (WS cannot set headers)."""
    try:
        payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            await websocket.close(code=1008)
            return
    except (JWTError, Exception):
        await websocket.close(code=1008)
        return
    await notif_manager.connect(user.id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive; client sends pings
    except WebSocketDisconnect:
        notif_manager.disconnect(user.id, websocket)


# Serve frontend (must be last — catches all unmatched paths)
@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
