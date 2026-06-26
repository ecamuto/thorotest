import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session
from jose import JWTError, jwt as jose_jwt

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
from .auth_utils import SECRET_KEY, ALGORITHM
from .gql_schema import graphql_router
from .routers import folders, tests, runs, pipelines, activity, auth, projects, categories, defects, integrations, tokens, webhooks, favorites, import_, attachments, admin, ai, notifications, audit_log, oauth, totp

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    _run_migrations()
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
async def insights(db: Session = Depends(get_db)):
    tests = db.query(models.Test).all()
    total = len(tests)
    pass_count = sum(1 for t in tests if t.status == "pass")
    auto_count = sum(1 for t in tests if t.auto)

    defects = db.query(models.Defect).all()
    open_defects = sum(1 for d in defects if d.status != "resolved")
    critical = sum(1 for d in defects if d.status != "resolved" and d.severity == "critical")
    high = sum(1 for d in defects if d.status != "resolved" and d.severity == "high")

    pass_rate = round(pass_count / total * 100, 1) if total > 0 else 0
    automation_rate = round(auto_count / total * 100) if total > 0 else 0

    top_folders = db.query(models.Folder).filter(models.Folder.parent_id == None).all()
    folder_coverage = []
    for f in top_folders:
        child_ids = [c.id for c in f.children]
        folder_tests = [t for t in tests if t.folder_id == f.id or t.folder_id in child_ids]
        f_total = len(folder_tests)
        f_pass = sum(1 for t in folder_tests if t.status == "pass")
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

    flaky_list = []
    for row in all_case_counts:
        if row.cnt < 2:
            continue
        fails = fail_map.get(row.test_id, 0)
        if fails == 0:
            continue
        rate = round(fails / row.cnt * 100)
        t = db.query(models.Test).filter(models.Test.id == row.test_id).first()
        if t:
            flaky_list.append({"id": t.id, "title": t.title, "fail_rate": rate, "total_runs": row.cnt})
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


# Aggregated initial-data endpoint (replaces window.TH_DATA)
@app.get("/api/initial-data")
async def initial_data(db: Session = Depends(get_db)):
    from .routers.folders import _build_tree

    all_folders = db.query(models.Folder).all()
    folder_tree = _build_tree(all_folders)

    all_tests = db.query(models.Test).all()
    tests_out = [
        {
            "id": t.id, "title": t.title, "folder": t.folder_id, "type": t.type,
            "status": t.status, "priority": t.priority, "owner": t.owner,
            "updated": t.updated_at, "lastRun": t.last_run_at, "duration": t.duration,
            "tags": t.tags or [], "auto": t.auto, "runner": t.runner,
        }
        for t in all_tests
    ]

    all_runs = db.query(models.Run).all()
    runs_out = [
        {
            "id": r.id, "name": r.name, "status": r.status, "progress": r.progress,
            "total": r.total, "passed": r.passed, "failed": r.failed, "blocked": r.blocked,
            "started": r.started, "owner": r.owner, "env": r.env, "branch": r.branch,
            "source_run_id": r.source_run_id,
        }
        for r in all_runs
    ]

    all_pipelines = db.query(models.Pipeline).all()
    pipelines_out = [
        {
            "id": p.id, "name": p.name, "platform": p.platform, "status": p.status,
            "duration": p.duration, "commit": p.commit, "author": p.author,
            "branch": p.branch, "when": p.when,
        }
        for p in all_pipelines
    ]

    all_activity = db.query(models.Activity).order_by(models.Activity.id.desc()).all()
    activity_out = [
        {"who": a.who, "what": a.what, "target": a.target, "detail": a.detail, "when": a.when}
        for a in all_activity
    ]

    all_defects = db.query(models.Defect).all()
    defects_out = [
        {"id": d.id, "title": d.title, "status": d.status, "severity": d.severity,
         "testId": d.test_id, "runId": d.run_id}
        for d in all_defects
    ]

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
        "projects": projects_out,
        "categories": categories_out,
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
