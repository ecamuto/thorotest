"""Custom field definitions — admin-managed extra fields for tests, defects
and requirements.

Definitions are global (one set per entity type). Values are stored per record
in the entity's `custom_fields` JSON column; the mutating routers call
`validate_and_merge()` so every write is checked against the definitions.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..db import get_db
from .. import models
from ..schemas import CustomFieldDefOut, CustomFieldDefCreate, CustomFieldDefUpdate
from ..auth_utils import require_role, get_current_user

router = APIRouter(tags=["custom-fields"])

ADMIN_ONLY = require_role("admin")

ENTITY_TYPES = {"test", "defect", "requirement"}
FIELD_TYPES = {"text", "number", "select", "date", "checkbox"}

_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _slugify(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")[:64]


def _validate_def(entity_type: str, field_type: str, options) -> None:
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"entity_type must be one of: {', '.join(sorted(ENTITY_TYPES))}")
    if field_type not in FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"field_type must be one of: {', '.join(sorted(FIELD_TYPES))}")
    if field_type == "select" and not options:
        raise HTTPException(status_code=400, detail="select fields need at least one option")


def _check_value(d: models.CustomFieldDef, v):
    """Validate one value against its definition. Returns the value to store."""
    if d.field_type == "text":
        if not isinstance(v, str):
            raise HTTPException(status_code=400, detail=f"'{d.key}' must be a string")
    elif d.field_type == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise HTTPException(status_code=400, detail=f"'{d.key}' must be a number")
    elif d.field_type == "checkbox":
        if not isinstance(v, bool):
            raise HTTPException(status_code=400, detail=f"'{d.key}' must be true or false")
    elif d.field_type == "date":
        if not isinstance(v, str) or not _DATE_RE.match(v):
            raise HTTPException(status_code=400, detail=f"'{d.key}' must be a date (YYYY-MM-DD)")
    elif d.field_type == "select":
        if v not in (d.options or []):
            raise HTTPException(status_code=400, detail=f"'{d.key}' must be one of: {', '.join(d.options or [])}")
    return v


def validate_and_merge(
    db: Session,
    entity_type: str,
    incoming: Optional[dict],
    existing: Optional[dict] = None,
    *,
    partial: bool = False,
) -> dict:
    """Validate incoming custom-field values and merge them over `existing`.

    - unknown keys → 400
    - type/option mismatches → 400
    - null value (or "" ) removes the key
    - required fields must be present after the merge; on partial updates the
      check only fires for keys the caller touched (so a PATCH that doesn't
      mention custom fields never fails on legacy records).
    """
    defs = db.query(models.CustomFieldDef).filter(models.CustomFieldDef.entity_type == entity_type).all()
    by_key = {d.key: d for d in defs}
    incoming = incoming or {}

    unknown = sorted(set(incoming) - set(by_key))
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown custom field(s): {', '.join(unknown)}")

    merged = dict(existing or {})
    for k, v in incoming.items():
        d = by_key[k]
        if v is None or v == "":
            if d.required:
                raise HTTPException(status_code=400, detail=f"'{k}' is required and cannot be cleared")
            merged.pop(k, None)
        else:
            merged[k] = _check_value(d, v)

    if not partial:
        missing = [d.key for d in defs if d.required and merged.get(d.key) in (None, "")]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing required custom field(s): {', '.join(sorted(missing))}")
    return merged


def diff_custom_fields(db: Session, entity_type: str, old: Optional[dict], new: Optional[dict]) -> list:
    """Per-key change entries for record history, labelled with the def's label."""
    labels = {
        d.key: d.label
        for d in db.query(models.CustomFieldDef).filter(models.CustomFieldDef.entity_type == entity_type).all()
    }
    old, new = old or {}, new or {}
    changes = []
    for k in sorted(set(old) | set(new)):
        if old.get(k) != new.get(k):
            changes.append({"field": labels.get(k, k), "old": old.get(k), "new": new.get(k)})
    return changes


@router.get("/custom-fields", response_model=List[CustomFieldDefOut])
def list_custom_fields(
    entity_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.CustomFieldDef)
    if entity_type:
        q = q.filter(models.CustomFieldDef.entity_type == entity_type)
    return q.order_by(models.CustomFieldDef.entity_type, models.CustomFieldDef.order, models.CustomFieldDef.id).all()


@router.post("/custom-fields", response_model=CustomFieldDefOut, status_code=201)
def create_custom_field(
    payload: CustomFieldDefCreate,
    db: Session = Depends(get_db),
    _: models.User = ADMIN_ONLY,
):
    _validate_def(payload.entity_type, payload.field_type, payload.options)
    key = (payload.key or _slugify(payload.label)).strip()
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="key must be lowercase letters, digits or _ (max 64 chars)")
    dup = (
        db.query(models.CustomFieldDef)
        .filter(models.CustomFieldDef.entity_type == payload.entity_type, models.CustomFieldDef.key == key)
        .first()
    )
    if dup:
        raise HTTPException(status_code=409, detail=f"Custom field '{key}' already exists for {payload.entity_type}")
    d = models.CustomFieldDef(
        entity_type=payload.entity_type,
        key=key,
        label=payload.label.strip() or key,
        field_type=payload.field_type,
        options=payload.options if payload.field_type == "select" else [],
        required=payload.required,
        order=payload.order,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.patch("/custom-fields/{def_id}", response_model=CustomFieldDefOut)
def update_custom_field(
    def_id: int,
    payload: CustomFieldDefUpdate,
    db: Session = Depends(get_db),
    _: models.User = ADMIN_ONLY,
):
    d = db.query(models.CustomFieldDef).filter(models.CustomFieldDef.id == def_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Custom field not found")
    data = payload.model_dump(exclude_unset=True)
    field_type = data.get("field_type", d.field_type)
    options = data.get("options", d.options)
    _validate_def(d.entity_type, field_type, options)
    if field_type != "select":
        data["options"] = []
    for field, value in data.items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/custom-fields/{def_id}", status_code=204)
def delete_custom_field(
    def_id: int,
    db: Session = Depends(get_db),
    _: models.User = ADMIN_ONLY,
):
    """Delete a definition. Stored values keep living in each record's JSON
    blob but are no longer validated, shown, or editable."""
    d = db.query(models.CustomFieldDef).filter(models.CustomFieldDef.id == def_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Custom field not found")
    db.delete(d)
    db.commit()
