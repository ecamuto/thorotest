import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import RunOut, RunDetailOut, RunCreate, DefectOut, StepResultOut, StepResultIn, RunCaseAssign, RunCaseOut
from ..auth_utils import require_role, get_current_user
from ..audit_utils import log_event, EVT_RUN_STARTED, EVT_RUN_COMPLETED
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
    )
    db.add(run)
    db.flush()

    for test_id in payload.test_ids:
        db.add(models.RunCase(run_id=run.id, test_id=test_id, status="pending"))

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
    )
    db.add(new_run)
    db.flush()
    for c in failed_cases:
        db.add(models.RunCase(run_id=new_run.id, test_id=c.test_id, status="pending"))
    db.commit()
    db.refresh(new_run)
    return new_run


@router.patch("/runs/{run_id}/cases/{case_id}", response_model=RunCaseOut)
def update_run_case(
    run_id: str,
    case_id: int,
    payload: RunCaseAssign,
    db: Session = Depends(get_db),
    _: models.User = LEAD_ROLES,
):
    rc = db.query(models.RunCase).filter(
        models.RunCase.id == case_id,
        models.RunCase.run_id == run_id,
    ).first()
    if not rc:
        raise HTTPException(status_code=404, detail="RunCase not found")
    rc.assigned_to = payload.assigned_to
    db.commit()
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
