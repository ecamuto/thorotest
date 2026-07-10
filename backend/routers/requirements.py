import csv
import io
import json
import random
import string
import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from .. import models
from ..schemas import RequirementOut, RequirementCreate, RequirementUpdate, RequirementCoverage
from ..auth_utils import require_role, get_current_user
from ..activity_utils import log_activity
from ..record_history import log_create, log_update, log_delete
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["requirements"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")

_TYPE_ALIASES = {"epic": "epic", "story": "story", "feature": "feature", "requirement": "feature", "req": "feature"}
_STATUS_ALIASES = {"active": "active", "draft": "draft", "done": "done", "closed": "done", "deprecated": "deprecated"}
_PRIORITY_ALIASES = {
    "low": "low", "p3": "low", "med": "med", "medium": "med", "p2": "med",
    "high": "high", "p1": "high", "critical": "critical", "crit": "critical", "p0": "critical",
}


def _split_test_ids(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    # CSV/string: split on comma, semicolon, or whitespace
    return [p.strip() for p in str(value).replace(";", ",").replace(" ", ",").split(",") if p.strip()]


def _normalize_req_row(row: dict) -> dict:
    title = str(row.get("title") or "").strip()
    if not title:
        raise ValueError("requirement missing required 'title'")
    return {
        "id": str(row["id"]).strip() if row.get("id") else None,
        "title": title,
        "type": _TYPE_ALIASES.get(str(row.get("type") or "feature").strip().lower(), "feature"),
        "status": _STATUS_ALIASES.get(str(row.get("status") or "active").strip().lower(), "active"),
        "priority": _PRIORITY_ALIASES.get(str(row.get("priority") or "med").strip().lower(), "med"),
        "owner": str(row["owner"]).strip() if row.get("owner") else None,
        "description": str(row["description"]).strip() if row.get("description") else None,
        "test_ids": _split_test_ids(row.get("tests") or row.get("test_ids")),
    }


def _parse_requirements_file(filename: str, content: bytes) -> tuple[list[dict], list[str]]:
    """Parse a YAML / JSON / CSV requirements file into normalized rows. Returns (rows, warnings)."""
    name = (filename or "").lower()
    text = content.decode("utf-8", errors="replace")
    warnings: list[str] = []
    raw_rows: list[dict] = []

    if name.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        raw_rows = [dict(r) for r in reader]
    elif name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"invalid JSON: {e}")
        raw_rows = data.get("requirements", data) if isinstance(data, dict) else data
    else:  # default to YAML (.yml/.yaml or unknown)
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"invalid YAML: {e}")
        raw_rows = data.get("requirements", []) if isinstance(data, dict) else (data or [])

    if not isinstance(raw_rows, list):
        raise HTTPException(status_code=400, detail="file must contain a list of requirements")

    rows: list[dict] = []
    for i, r in enumerate(raw_rows):
        if not isinstance(r, dict):
            warnings.append(f"row {i + 1}: skipped (not a mapping)")
            continue
        try:
            rows.append(_normalize_req_row(r))
        except ValueError as e:
            warnings.append(f"row {i + 1}: {e}")
    return rows, warnings


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


@router.get("/tests/{test_id}/requirements", response_model=List[RequirementOut])
def list_test_requirements(test_id: str, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    t = db.query(models.Test).filter(models.Test.id == test_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Test not found")
    return [_serialize(r) for r in t.requirements]


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
    log_create(db, "requirement", req_id, current_user)
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.post("/requirements/import")
async def import_requirements(
    file: UploadFile = File(...),
    current_user: models.User = WRITE_ROLES,
    db: Session = Depends(get_db),
):
    """Bulk import requirements from a YAML / JSON / CSV file (Tests-as-Code parity).

    Upsert by `id` when present, else by title. Linked tests are matched by id;
    unknown test ids are reported in warnings rather than failing the import.
    """
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    rows, warnings = _parse_requirements_file(file.filename or "", content)
    created_by = current_user.display_name or current_user.username
    stats = {"created": 0, "updated": 0, "skipped": 0}

    for row in rows:
        existing = None
        if row["id"]:
            existing = db.query(models.Requirement).filter(models.Requirement.id == row["id"]).first()
        if not existing:
            existing = db.query(models.Requirement).filter(models.Requirement.title == row["title"]).first()

        # Resolve linked tests; warn on unknown ids without aborting.
        tests = []
        if row["test_ids"]:
            found = db.query(models.Test).filter(models.Test.id.in_(row["test_ids"])).all()
            found_ids = {t.id for t in found}
            for missing in set(row["test_ids"]) - found_ids:
                warnings.append(f"{row['id'] or row['title']}: unknown test id '{missing}'")
            tests = found

        if existing:
            existing.title = row["title"]
            existing.type = row["type"]
            existing.status = row["status"]
            existing.priority = row["priority"]
            if row["owner"] is not None:
                existing.owner = row["owner"]
            if row["description"] is not None:
                existing.description = row["description"]
            if row["test_ids"]:
                existing.tests = tests
            stats["updated"] += 1
        else:
            req_id = row["id"]
            if not req_id or db.query(models.Requirement).filter(models.Requirement.id == req_id).first():
                req_id = "REQ-" + "".join(random.choices(string.digits, k=4))
                while db.query(models.Requirement).filter(models.Requirement.id == req_id).first():
                    req_id = "REQ-" + "".join(random.choices(string.digits, k=4))
            r = models.Requirement(
                id=req_id, title=row["title"], type=row["type"], status=row["status"],
                priority=row["priority"], owner=row["owner"], description=row["description"],
                created_at="just now", created_by=created_by, tests=tests,
            )
            db.add(r)
            stats["created"] += 1

    log_activity(db, created_by, "imported requirements", file.filename or "file",
                 f"{stats['created']} created, {stats['updated']} updated")
    db.commit()
    return {"ok": True, "imported": stats, "warnings": warnings}


@router.patch("/requirements/{req_id}", response_model=RequirementOut)
def update_requirement(req_id: str, payload: RequirementUpdate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    data = payload.model_dump(exclude_unset=True)
    if "test_ids" in data:
        r.tests = _resolve_tests(db, data.pop("test_ids") or [])
    log_update(db, "requirement", req_id, current_user, r, data)
    for field, value in data.items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return _serialize(r)


@router.delete("/requirements/{req_id}", status_code=204)
def delete_requirement(req_id: str, db: Session = Depends(get_db), current_user: models.User = ADMIN_ONLY):
    r = db.query(models.Requirement).filter(models.Requirement.id == req_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Requirement not found")
    db.delete(r)
    log_delete(db, "requirement", req_id, current_user)
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
