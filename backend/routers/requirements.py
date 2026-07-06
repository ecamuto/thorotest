import random
import string
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from .. import models
from ..schemas import RequirementOut, RequirementCreate, RequirementUpdate, RequirementCoverage
from ..auth_utils import require_role, get_current_user
from ..activity_utils import log_activity
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["requirements"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")


def _coverage(req: models.Requirement) -> RequirementCoverage:
    """Coverage from the linked tests' current status (same status vocab overview uses)."""
    tests = req.tests
    linked = len(tests)
    passed = sum(1 for t in tests if t.status == "pass")
    failed = sum(1 for t in tests if t.status == "fail")
    untested = linked - passed - failed
    pass_rate = round(passed / linked, 4) if linked else 0.0
    return RequirementCoverage(linked=linked, passed=passed, failed=failed, untested=untested, pass_rate=pass_rate)


def _serialize(req: models.Requirement) -> RequirementOut:
    return RequirementOut(
        id=req.id, title=req.title, type=req.type, status=req.status, priority=req.priority,
        description=req.description, owner=req.owner, created_at=req.created_at, created_by=req.created_by,
        external_provider=req.external_provider, external_key=req.external_key, external_url=req.external_url,
        test_ids=req.test_ids, coverage=_coverage(req),
    )


def _resolve_tests(db: Session, test_ids: List[str]) -> List[models.Test]:
    if not test_ids:
        return []
    found = db.query(models.Test).filter(models.Test.id.in_(test_ids)).all()
    missing = set(test_ids) - {t.id for t in found}
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown test id(s): {', '.join(sorted(missing))}")
    return found


@router.get("/requirements", response_model=List[RequirementOut])
def list_requirements(
    response: Response,
    status: Optional[str] = None,
    type: Optional[str] = None,
    covered: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.Requirement)
    if status and status != "all":
        q = q.filter(models.Requirement.status == status)
    if type and type != "all":
        q = q.filter(models.Requirement.type == type)
    if search:
        q = q.filter(
            or_(
                models.Requirement.title.ilike(f"%{search}%"),
                models.Requirement.id.ilike(f"%{search}%"),
            )
        )
    rows = paginate(q.order_by(models.Requirement.id.desc()), response, limit, offset)
    out = [_serialize(r) for r in rows]
    if covered is not None:
        out = [r for r in out if (r.coverage.linked > 0) == covered]
    return out


@router.get("/requirements/{req_id}", response_model=RequirementOut)
def get_requirement(req_id: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    return _serialize(r)


@router.post("/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(
    payload: RequirementCreate,
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    req_id = "REQ-" + "".join(random.choices(string.digits, k=4))
    while db.query(models.Requirement).filter(models.Requirement.id == req_id).first():
        req_id = "REQ-" + "".join(random.choices(string.digits, k=4))
    created_by = current_user.display_name or current_user.username
    r = models.Requirement(
        id=req_id,
        title=payload.title,
        type=payload.type,
        status=payload.status,
        priority=payload.priority,
        description=payload.description,
        owner=payload.owner,
        created_at="just now",
        created_by=created_by,
    )
    r.tests = _resolve_tests(db, payload.test_ids)
    db.add(r)
    log_activity(db, created_by, "created requirement", req_id, payload.title)
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.patch("/requirements/{req_id}", response_model=RequirementOut)
def update_requirement(req_id: str, payload: RequirementUpdate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    data = payload.model_dump(exclude_unset=True)
    if "test_ids" in data:
        r.tests = _resolve_tests(db, data.pop("test_ids") or [])
    for field, value in data.items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.delete("/requirements/{req_id}", status_code=204)
def delete_requirement(req_id: str, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    db.delete(r)
    db.commit()


@router.post("/requirements/{req_id}/tests/{test_id}", response_model=RequirementOut)
def link_test(req_id: str, test_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    if t not in r.tests:
        r.tests.append(t)
        db.commit()
        db.refresh(r)
    return _serialize(r)


@router.delete("/requirements/{req_id}/tests/{test_id}", response_model=RequirementOut)
def unlink_test(req_id: str, test_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if t and t in r.tests:
        r.tests.remove(t)
        db.commit()
        db.refresh(r)
    return _serialize(r)
