import random
import string
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from .. import models
from ..schemas import DefectOut, DefectCreate, DefectUpdate
from ..auth_utils import require_role

router = APIRouter(tags=["defects"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")


@router.get("/defects", response_model=List[DefectOut])
def list_defects(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    test_id: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
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
    return q.order_by(models.Defect.id.desc()).all()


@router.get("/defects/{defect_id}", response_model=DefectOut)
def get_defect(defect_id: str, db: Session = Depends(get_db)):
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
    db.commit()
    db.refresh(d)
    return d


@router.patch("/defects/{defect_id}", response_model=DefectOut)
def update_defect(defect_id: str, payload: DefectUpdate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/defects/{defect_id}", status_code=204)
def delete_defect(defect_id: str, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    d = db.query(models.Defect).filter(models.Defect.id == defect_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Defect not found")
    db.delete(d)
    db.commit()
