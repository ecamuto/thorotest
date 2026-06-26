from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..db import get_db
from .. import models
from ..schemas import ProjectOut, ProjectCreate, ProjectUpdate
from ..auth_utils import require_role, get_current_user

router = APIRouter(tags=["projects"])

ADMIN_ONLY = require_role("admin")


@router.get("/projects", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return db.query(models.Project).all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    if db.query(models.Project).filter(models.Project.id == payload.id).first():
        raise HTTPException(status_code=409, detail="Project ID already exists")
    project = models.Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
