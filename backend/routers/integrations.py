from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import IntegrationOut, IntegrationCreate, IntegrationUpdate

router = APIRouter(tags=["integrations"])


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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(intg, field, value)
    db.commit()
    db.refresh(intg)
    return intg


@router.delete("/integrations/{intg_id}", status_code=204)
def delete_integration(intg_id: str, db: Session = Depends(get_db)):
    intg = db.query(models.Integration).filter(models.Integration.id == intg_id).first()
    if not intg:
        raise HTTPException(status_code=404, detail="Integration not found")
    db.delete(intg)
    db.commit()
