from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import IntegrationOut, IntegrationCreate, IntegrationUpdate
from ..auth_utils import require_role
from ..github_sync import sync_integration

router = APIRouter(tags=["integrations"])

WRITE_ROLES = require_role("admin", "manager")


@router.get("/integrations", response_model=List[IntegrationOut])
def list_integrations(db: Session = Depends(get_db)):
    return db.query(models.Integration).all()


@router.post("/integrations", response_model=IntegrationOut, status_code=201)
def create_integration(payload: IntegrationCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Integration).filter(models.Integration.id == payload.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Integration ID already exists")
    intg = models.Integration(**payload.model_dump())
    db.add(intg)
    db.commit()
    db.refresh(intg)
    return intg


@router.patch("/integrations/{intg_id}", response_model=IntegrationOut)
def update_integration(intg_id: str, payload: IntegrationUpdate, db: Session = Depends(get_db)):
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    updates = payload.model_dump(exclude_unset=True)
    if "config" in updates and updates["config"] is not None:
        # Merge so a redacted/empty token from the client never wipes the stored one.
        merged = dict(intg.config or {})
        incoming = updates.pop("config")
        new_token = incoming.get("token")
        merged.update(incoming)
        if not new_token:
            merged["token"] = (intg.config or {}).get("token", "")
        merged.pop("token_set", None)
        intg.config = merged
    for field, value in updates.items():
        setattr(intg, field, value)
    db.commit()
    db.refresh(intg)
    return intg


@router.post("/integrations/{intg_id}/sync")
def sync_integration_now(intg_id: str, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    """Pull YAML tests from the integration's git repo (read-only) and upsert them."""
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    # sync_integration validates the config points at a github.com repo.
    try:
        stats = sync_integration(db, intg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        intg.status = "error"
        db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "last_sync": intg.last_sync, **stats}


@router.delete("/integrations/{intg_id}", status_code=204)
def delete_integration(intg_id: str, db: Session = Depends(get_db)):
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    db.delete(intg)
    db.commit()
