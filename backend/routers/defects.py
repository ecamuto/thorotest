import random
import string
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from .. import models
from ..schemas import DefectOut, DefectCreate, DefectUpdate
from ..auth_utils import require_role, get_current_user
from ..activity_utils import log_activity, actor_name
from ..record_history import log_create, log_update, log_delete
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["defects"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")


@router.get("/defects", response_model=List[DefectOut])
def list_defects(
    response: Response,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    test_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.Defect)
    if status and status != "all":
        q = q.filter(models.Defect.status == status)
    if severity and severity != "all":
        q = q.filter(models.Defect.severity == severity)
    if test_id:
        q = q.filter(models.Defect.test_id == test_id)
    if search:
        q = q.filter(
            or_(
                models.Defect.title.ilike(f"%{search}%"),
                models.Defect.id.ilike(f"%{search}%"),
            )
        )
    return paginate(q.order_by(models.Defect.id.desc()), response, limit, offset)


@router.get("/defects/{defect_id}", response_model=DefectOut)
def get_defect(defect_id: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    return d


@router.post("/defects", response_model=DefectOut, status_code=201)
def create_defect(
    payload: DefectCreate,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    bug_id = "BUG-" + "".join(random.choices(string.digits, k=4))
    while db.query(models.Defect).filter(models.Defect.id == bug_id).first():
        bug_id = "BUG-" + "".join(random.choices(string.digits, k=4))
    created_by = current_user.display_name or current_user.username
    d = models.Defect(
        id=bug_id,
        title=payload.title,
        severity=payload.severity,
        description=payload.description,
        test_id=payload.test_id,
        run_id=payload.run_id,
        status="open",
        created_at="just now",
        created_by=created_by,
    )
    db.add(d)
    log_activity(db, created_by, "filed defect", bug_id, payload.title)
    log_create(db, "defect", bug_id, current_user)
    db.commit()
    db.refresh(d)
    return d


@router.patch("/defects/{defect_id}", response_model=DefectOut)
def update_defect(defect_id: str, payload: DefectUpdate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    data = payload.model_dump(exclude_unset=True)
    log_update(db, "defect", defect_id, current_user, d, data)
    for field, value in data.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    return d


PUSH_ROLES = require_role("admin", "manager")


@router.post("/defects/{defect_id}/push", response_model=DefectOut)
def push_defect(defect_id: str, current_user: models.User = PUSH_ROLES, db: Session = Depends(get_db)):
    """Create a Jira bug from this defect and store the external link on it."""
    from ..jira_sync import push_defect_to_jira

    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    if d.external_key:
        raise HTTPException(status_code=409, detail=f"Defect already linked to {d.external_key}")

    intg = db.query(models.Integration).filter(models.Integration.type == "jira").first()
    if not intg:
        raise HTTPException(status_code=400, detail="No Jira integration configured")

    try:
        push_defect_to_jira(db, intg, d)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    actor = current_user.display_name or current_user.username
    log_activity(db, actor, "pushed defect to Jira", d.id, d.external_key or "")
    db.commit()
    return d


@router.delete("/defects/{defect_id}", status_code=204)
def delete_defect(defect_id: str, db: Session = Depends(get_db), current_user: models.User = ADMIN_ONLY):
    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    db.delete(d)
    log_delete(db, "defect", defect_id, current_user)
    db.commit()
