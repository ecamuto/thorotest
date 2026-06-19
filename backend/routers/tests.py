import asyncio
import csv
import io
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from .. import models
from ..schemas import TestOut, TestCreate, TestUpdate, BulkAction, DefectOut, CommentOut, CommentCreate, TestStepOut, TestStepIn
from ..auth_utils import require_role
from ..notifications import _notify_comment_event
from ..audit_utils import log_event, EVT_TEST_CREATED, EVT_TEST_UPDATED, EVT_TEST_DELETED

router = APIRouter(tags=["tests"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")


@router.get("/tests", response_model=List[TestOut])
def list_tests(
    folder_id: Optional[str] = None,
    search: Optional[str] = None,
    status: Optional[str] = None,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Test)
    if folder_id:
        child_ids = [c.id for c in db.query(models.Folder).filter(models.Folder.parent_id == folder_id).all()]
        q = q.filter(models.Test.folder_id.in_([folder_id] + child_ids))
    if search:
        q = q.filter(or_(models.Test.title.ilike(f"%{search}%"), models.Test.id.ilike(f"%{search}%")))
    if status and status != "all":
        q = q.filter(models.Test.status == status)
    if type and type != "all":
        q = q.filter(models.Test.type == type)
    return q.all()


@router.post("/tests/bulk")
def bulk_tests(body: BulkAction, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    tests = db.query(models.Test).filter(models.Test.id.in_(body.ids)).all()
    if body.action == "delete":
        for t in tests:
            db.delete(t)
    elif body.action == "update" and body.payload:
        for t in tests:
            data = body.payload.model_dump(exclude_unset=True)
            data.pop("category_ids", None)
            for field, value in data.items():
                setattr(t, field, value)
    db.commit()
    return {"affected": len(tests)}


@router.get("/tests/export")
def export_tests(
    folder_id: Optional[str] = None,
    format: str = "csv",
    db: Session = Depends(get_db),
    current_user=require_role("admin", "manager", "tester", "viewer"),
):
    """Export test library as CSV. Filters by folder_id if provided (respects navigation context)."""
    from sqlalchemy.orm import joinedload

    if format != "csv":
        raise HTTPException(status_code=400, detail="format must be 'csv'")

    query = db.query(models.Test).options(
        joinedload(models.Test.steps),
        joinedload(models.Test.folder_rel),
    )
    if folder_id:
        query = query.filter(models.Test.folder_id == folder_id)

    tests = query.all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["title", "folder", "priority", "status", "steps_count", "created_at"])
    for t in tests:
        writer.writerow([
            t.title,
            t.folder_rel.name if t.folder_rel else "",
            t.priority or "",
            t.status or "",
            len(t.steps),
            t.updated_at or "",  # Test has no created_at column; updated_at used as substitute
        ])
    content = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tests-export.csv"},
    )


@router.get("/tests/{test_id}", response_model=TestOut)
def get_test(test_id: str, db: Session = Depends(get_db)):
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    return t


@router.post("/tests", response_model=TestOut, status_code=201)
def create_test(payload: TestCreate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    test_id = payload.id or f"TC-{uuid.uuid4().hex[:8].upper()}"
    if db.query(models.Test).filter(models.Test.id == test_id).first():
        raise HTTPException(status_code=409, detail="Test ID already exists")
    data = payload.model_dump()
    data["id"] = test_id
    t = models.Test(**data)
    db.add(t)
    db.commit()
    db.refresh(t)
    log_event(
        EVT_TEST_CREATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} created test '{t.title}'",
        target_type="test",
        target_id=str(t.id),
    )
    return t


@router.patch("/tests/{test_id}", response_model=TestOut)
def update_test(test_id: str, payload: TestUpdate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    data = payload.model_dump(exclude_unset=True)
    category_ids = data.pop("category_ids", None)
    for field, value in data.items():
        setattr(t, field, value)
    if category_ids is not None:
        t.categories = db.query(models.Category).filter(models.Category.id.in_(category_ids)).all()
    db.commit()
    db.refresh(t)
    log_event(
        EVT_TEST_UPDATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} updated test '{t.title}'",
        target_type="test",
        target_id=str(t.id),
    )
    return t


@router.delete("/tests/{test_id}", status_code=204)
def delete_test(test_id: str, db: Session = Depends(get_db), current_user: models.User = ADMIN_ONLY):
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    test_title = t.title   # capture before delete
    db.delete(t)
    db.commit()
    log_event(
        EVT_TEST_DELETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} deleted test '{test_title}'",
        target_type="test",
        target_id=str(test_id),
    )


@router.get("/tests/{test_id}/history")
def get_test_history(test_id: str, db: Session = Depends(get_db)):
    cases = (
        db.query(models.RunCase)
        .filter(models.RunCase.test_id == test_id)
        .all()
    )
    result = []
    for c in cases:
        run = c.run
        result.append({
            "run_id": run.id,
            "run_name": run.name,
            "case_status": c.status,
            "env": run.env,
            "branch": run.branch,
            "started": run.started,
            "duration": c.test.duration if c.test else None,
        })
    return result


@router.get("/tests/{test_id}/defects", response_model=List[DefectOut])
def get_test_defects(test_id: str, db: Session = Depends(get_db)):
    return db.query(models.Defect).filter(models.Defect.test_id == test_id).all()



@router.get("/tests/{test_id}/comments", response_model=List[CommentOut])
def get_comments(test_id: str, db: Session = Depends(get_db)):
    return db.query(models.Comment).filter(models.Comment.test_id == test_id).all()


@router.post("/tests/{test_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    test_id: str,
    payload: CommentCreate,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    if not db.query(models.Test).filter(models.Test.id == test_id).first():
        raise HTTPException(status_code=404, detail="Test not found")
    # Use payload.who if explicitly provided (not the schema default), else use auth user's name
    if payload.who and payload.who != "You":
        who = payload.who
    else:
        who = current_user.display_name or current_user.username or "You"
    c = models.Comment(test_id=test_id, who=who, text=payload.text, when="just now")
    db.add(c)
    db.commit()
    db.refresh(c)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_notify_comment_event(test_id, current_user.username))
    except RuntimeError:
        pass  # No running loop in sync test context — skip notification
    return c


@router.get("/tests/{test_id}/steps", response_model=List[TestStepOut])
def list_steps(test_id: str, db: Session = Depends(get_db)):
    if not db.query(models.Test).filter(models.Test.id == test_id).first():
        raise HTTPException(status_code=404, detail="Test not found")
    return (
        db.query(models.TestStep)
        .filter(models.TestStep.test_id == test_id)
        .order_by(models.TestStep.order)
        .all()
    )


@router.patch("/tests/{test_id}/steps", response_model=List[TestStepOut])
def replace_steps(test_id: str, steps: List[TestStepIn], db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    if not db.query(models.Test).filter(models.Test.id == test_id).first():
        raise HTTPException(status_code=404, detail="Test not found")
    # Atomic replace: delete all existing, insert new in order
    db.query(models.TestStep).filter(models.TestStep.test_id == test_id).delete()
    for i, s in enumerate(steps):
        db.add(models.TestStep(
            test_id=test_id,
            order=i + 1,
            action=s.action,
            expected_result=s.expected_result,
        ))
    db.commit()
    return (
        db.query(models.TestStep)
        .filter(models.TestStep.test_id == test_id)
        .order_by(models.TestStep.order)
        .all()
    )
