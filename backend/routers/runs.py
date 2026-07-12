import asyncio
import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import RunOut, RunDetailOut, RunCreate, DefectOut, StepResultOut, StepResultIn, RunCaseAssign, RunCaseUpdate, RunCaseOut
from ..auth_utils import require_role, get_current_user
from ..audit_utils import log_event, EVT_RUN_STARTED, EVT_RUN_COMPLETED
from ..activity_utils import log_activity, actor_name
from ..ws_manager import manager
from ..notifications import _notify_run_events, _fire_webhooks, _notify_assignment
from ._pagination import paginate, MAX_LIMIT
from fpdf import FPDF
from fpdf.fonts import FontFace

router = APIRouter(tags=["runs"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")
LEAD_ROLES = require_role("admin", "manager")


@router.get("/runs", response_model=List[RunOut])
def list_runs(
    response: Response,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return paginate(db.query(models.Run).order_by(models.Run.id), response, limit, offset)


@router.get("/runs/my-cases")
def get_my_cases(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    cases = (
        db.query(models.RunCase)
        .join(models.Run)
        .options(joinedload(models.RunCase.run), joinedload(models.RunCase.test))
        .filter(
            models.RunCase.assigned_to == current_user.username,
            models.Run.status.in_(["running", "paused", "pending"]),
        )
        .all()
    )
    runs_map = {}
    for c in cases:
        rid = c.run_id
        if rid not in runs_map:
            runs_map[rid] = {
                "run": {"id": c.run.id, "name": c.run.name, "status": c.run.status,
                        "progress": c.run.progress, "total": c.run.total,
                        "passed": c.run.passed, "failed": c.run.failed, "blocked": c.run.blocked,
                        "started": c.run.started, "owner": c.run.owner,
                        "env": c.run.env, "branch": c.run.branch,
                        "source_run_id": c.run.source_run_id},
                "cases": []
            }
        runs_map[rid]["cases"].append({
            "id": c.id, "test_id": c.test_id,
            "title": c.test.title if c.test else c.test_id,
            "status": c.status, "assigned_to": c.assigned_to,
        })
    return list(runs_map.values())


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    from sqlalchemy.orm import joinedload
    r = (
        db.query(models.Run)
        .options(joinedload(models.Run.cases).joinedload(models.RunCase.test))
        .filter(models.Run.id == run_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": r.id, "name": r.name, "status": r.status, "progress": r.progress,
        "total": r.total, "passed": r.passed, "failed": r.failed, "blocked": r.blocked,
        "started": r.started, "owner": r.owner, "env": r.env, "branch": r.branch,
        "source_run_id": r.source_run_id,
        "cases": [
            {
                "id": c.id, "run_id": c.run_id, "test_id": c.test_id,
                "status": c.status,
                "assigned_to": c.assigned_to,
                "title": c.test.title if c.test else c.test_id,
                "duration": (c.test.duration if c.test and c.test.duration else "—"),
            }
            for c in r.cases
        ],
    }


@router.post("/runs", response_model=RunOut, status_code=201)
def create_run(payload: RunCreate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    if db.query(models.Run).filter(models.Run.id == payload.id).first():
        raise HTTPException(status_code=409, detail="Run ID already exists")

    run = models.Run(
        id=payload.id, name=payload.name, status=payload.status,
        total=payload.total or len(payload.test_ids),
        owner=payload.owner, env=payload.env, branch=payload.branch,
        started="just now",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(run)
    db.flush()

    for test_id in payload.test_ids:
        db.add(models.RunCase(run_id=run.id, test_id=test_id, status="pending"))

    log_activity(db, actor_name(current_user), "started run", run.id, run.name)
    db.commit()
    db.refresh(run)
    log_event(
        EVT_RUN_STARTED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} started run '{run.name}'",
        target_type="run",
        target_id=str(run.id),
    )
    return run


@router.post("/runs/{run_id}/retest", response_model=RunOut, status_code=201)
def retest_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    _: models.User = WRITE_ROLES,
):
    import uuid
    source = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Run not found")
    failed_cases = [c for c in source.cases if c.status in ("fail", "blocked")]
    if not failed_cases:
        raise HTTPException(status_code=400, detail="No failed or blocked cases to retest")
    new_id = "R-" + str(uuid.uuid4())[:8].upper()
    new_run = models.Run(
        id=new_id,
        name=f"Retest: {source.name}",
        source_run_id=source.id,
        status="running",
        total=len(failed_cases),
        owner=current_user.username,
        started="just now",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(new_run)
    db.flush()
    for c in failed_cases:
        db.add(models.RunCase(run_id=new_run.id, test_id=c.test_id, status="pending"))
    log_activity(db, actor_name(current_user), "started retest", new_run.id, new_run.name)
    db.commit()
    db.refresh(new_run)
    return new_run


_VALID_CASE_STATUS = {"pass", "fail", "blocked", "skip", "pending"}


@router.patch("/runs/{run_id}/cases/{case_id}", response_model=RunCaseOut)
async def update_run_case(
    run_id: str,
    case_id: int,
    payload: RunCaseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = WRITE_ROLES,
):
    """Update a case in a run. Assignment (`assigned_to`) and manual result
    (`status` + optional `actual_result`) share this endpoint. Marking a
    result recomputes the run's counters/progress and broadcasts a live
    update over the run WebSocket — this is the real-time run path (the
    DEMO_MODE simulator emits the same messages, but here results are real)."""
    rc = db.query(models.RunCase).filter(
        models.RunCase.id == case_id,
        models.RunCase.run_id == run_id,
    ).first()
    if not rc:
        raise HTTPException(status_code=404, detail="RunCase not found")

    fields = payload.model_fields_set
    assignee_changed = False
    new_assignee = None
    if "assigned_to" in fields:
        # Assignment stays a lead action; result marking is open to testers.
        if current_user.role not in ("admin", "manager"):
            raise HTTPException(status_code=403, detail="Only leads can assign cases")
        assignee_changed = (payload.assigned_to or None) != (rc.assigned_to or None)
        new_assignee = payload.assigned_to
        rc.assigned_to = payload.assigned_to
    if "actual_result" in fields:
        rc.actual_result = payload.actual_result

    status_changed = "status" in fields and payload.status is not None
    if status_changed:
        if payload.status not in _VALID_CASE_STATUS:
            raise HTTPException(status_code=400, detail=f"Invalid status: {payload.status}")
        rc.status = payload.status

    db.commit()

    if assignee_changed and new_assignee:
        case_title = (rc.test.title if rc.test else None) or rc.test_id
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_notify_assignment(
                "test case", case_title, f"#/runs/{run_id}", new_assignee, current_user.username))
        except RuntimeError:
            pass

    if not status_changed:
        db.refresh(rc)
        return rc

    # ── Recompute run counters + progress from all cases ──────────
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    cases = db.query(models.RunCase).filter(models.RunCase.run_id == run_id).all()
    total = run.total or len(cases)
    run.passed = sum(1 for c in cases if c.status == "pass")
    run.failed = sum(1 for c in cases if c.status == "fail")
    run.blocked = sum(1 for c in cases if c.status in ("blocked", "skip"))
    done = sum(1 for c in cases if c.status != "pending")
    complete = done >= total and total > 0
    run.progress = 100 if complete else (int(done / total * 100) if total else 0)
    if run.status in (None, "pending"):
        run.status = "running"
    if complete:
        run.status = "fail" if run.failed > 0 else "pass"
    db.commit()

    test = db.query(models.Test).filter(models.Test.id == rc.test_id).first()
    await manager.broadcast(run_id, {
        "event": "step",
        "caseId": rc.id,
        "testId": rc.test_id,
        "testTitle": test.title if test else rc.test_id,
        "status": rc.status,
        "progress": run.progress,
        "passed": run.passed,
        "failed": run.failed,
        "blocked": run.blocked,
        "done": done,
        "total": total,
    })

    if complete:
        await manager.broadcast(run_id, {
            "event": "complete",
            "status": run.status,
            "passed": run.passed,
            "failed": run.failed,
            "blocked": run.blocked,
        })
        log_event(
            EVT_RUN_COMPLETED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            description=f"Run '{run.name}' completed: {run.passed} passed, {run.failed} failed",
            target_type="run",
            target_id=str(run.id),
        )
        asyncio.create_task(_notify_run_events(run_id))
        asyncio.create_task(_fire_webhooks(run_id))

    db.refresh(rc)
    return rc


@router.get("/runs/{run_id}/defects", response_model=List[DefectOut])
def get_run_defects(run_id: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    if not db.query(models.Run).filter(models.Run.id == run_id).first():
        raise HTTPException(status_code=404, detail="Run not found")
    return db.query(models.Defect).filter(models.Defect.run_id == run_id).all()


@router.patch("/runs/{run_id}/status")
def update_run_status(run_id: str, status: str, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    r = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    r.status = status
    if status == "completed":
        log_activity(db, actor_name(current_user), "completed run", r.id,
                     f"{r.name} — {r.passed} passed / {r.failed} failed")
    else:
        log_activity(db, actor_name(current_user), "updated run", r.id, f"{r.name} → {status}")
    db.commit()
    if status == "completed":
        log_event(
            EVT_RUN_COMPLETED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            description=f"{current_user.email} completed run '{r.name}'",
            target_type="run",
            target_id=str(run_id),
        )
    return {"id": run_id, "status": status}


STATUS_COLORS = {
    "pass":    (40, 167, 69),
    "fail":    (220, 53, 69),
    "skip":    (108, 117, 125),
    "blocked": (255, 143, 0),
    "pending": (200, 200, 200),
    "not_run": (200, 200, 200),
}

_REPLACEMENTS = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}

def _safe(text: str) -> str:
    if not text:
        return ""
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _build_run_pdf(run, cases) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, _safe(run.name or f"Run {run.id}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    total = len(cases)
    passed  = sum(1 for c in cases if c.status == "pass")
    failed  = sum(1 for c in cases if c.status == "fail")
    skipped = sum(1 for c in cases if c.status == "skip")
    blocked = sum(1 for c in cases if c.status == "blocked")
    pct = round(passed / total * 100) if total > 0 else 0

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    for label, count in [("Pass", passed), ("Fail", failed), ("Skip", skipped), ("Blocked", blocked)]:
        pdf.cell(40, 6, f"{label}: {count}")
    pdf.cell(0, 6, f"Pass rate: {pct}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    with pdf.table(col_widths=(70, 20, 30, 25, 45)) as table:
        header = table.row()
        for h in ["Test Name", "Status", "Assigned To", "Duration", "Actual Result"]:
            header.cell(h)
        pdf.set_font("Helvetica", "", 9)
        for c in cases:
            color = STATUS_COLORS.get(c.status, (200, 200, 200))
            style = FontFace(fill_color=color)
            row = table.row()
            row.cell(_safe(c.test.title if c.test else c.test_id))
            row.cell(c.status, style=style)
            row.cell(_safe(c.assigned_to or ""))
            row.cell(_safe(c.test.duration if c.test else ""))
            row.cell(_safe(c.actual_result or ""))

    return bytes(pdf.output())


@router.get("/runs/{run_id}/export")
def export_run(
    run_id: str,
    format: str = "csv",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from sqlalchemy.orm import joinedload
    run = (
        db.query(models.Run)
        .options(joinedload(models.Run.cases).joinedload(models.RunCase.test))
        .filter(models.Run.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    cases = run.cases

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["test_name", "status", "assigned_to", "duration", "actual_result"])
        for c in cases:
            writer.writerow([
                c.test.title if c.test else c.test_id,
                c.status,
                c.assigned_to or "",
                c.test.duration if c.test else "",
                c.actual_result or "",
            ])
        content = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=run-{run_id}-export.csv"},
        )
    elif format == "pdf":
        pdf_bytes = _build_run_pdf(run, cases)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=run-{run_id}-report.pdf"},
        )
    else:
        raise HTTPException(status_code=400, detail="format must be 'csv' or 'pdf'")


@router.get("/runs/{run_id}/cases/{case_id}/steps", response_model=List[StepResultOut])
def list_step_results(run_id: str, case_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Return step results for a run case, creating pending records if none exist yet."""
    rc = db.query(models.RunCase).filter(
        models.RunCase.id == case_id,
        models.RunCase.run_id == run_id,
    ).first()
    if not rc:
        raise HTTPException(status_code=404, detail="RunCase not found")

    # Ensure StepResult rows exist for all steps of the associated test
    existing_ids = {sr.test_step_id for sr in rc.step_results}
    test_steps = (
        db.query(models.TestStep)
        .filter(models.TestStep.test_id == rc.test_id)
        .order_by(models.TestStep.order)
        .all()
    )
    for ts in test_steps:
        if ts.id not in existing_ids:
            db.add(models.StepResult(run_case_id=case_id, test_step_id=ts.id, status="pending"))
    db.commit()

    return (
        db.query(models.StepResult)
        .join(models.TestStep)
        .filter(models.StepResult.run_case_id == case_id)
        .order_by(models.TestStep.order)
        .all()
    )


@router.patch("/runs/{run_id}/cases/{case_id}/steps/{step_id}", response_model=StepResultOut)
def update_step_result(
    run_id: str,
    case_id: int,
    step_id: int,
    payload: StepResultIn,
    db: Session = Depends(get_db),
    _: models.User = WRITE_ROLES,
):
    rc = db.query(models.RunCase).filter(
        models.RunCase.id == case_id,
        models.RunCase.run_id == run_id,
    ).first()
    if not rc:
        raise HTTPException(status_code=404, detail="RunCase not found")

    sr = db.query(models.StepResult).filter_by(run_case_id=case_id, test_step_id=step_id).first()
    if not sr:
        sr = models.StepResult(run_case_id=case_id, test_step_id=step_id)
        db.add(sr)
    sr.status = payload.status
    sr.actual_result = payload.actual_result
    db.commit()
    db.refresh(sr)
    return sr
