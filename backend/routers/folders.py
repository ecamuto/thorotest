from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import FolderOut, FolderCreate, FolderUpdate
from ..auth_utils import require_role

router = APIRouter(tags=["folders"])

WRITE_ROLES = require_role("admin", "manager", "tester")
ADMIN_ONLY = require_role("admin")


def _build_tree(folders: list, parent_id=None) -> list:
    result = []
    for f in folders:
        if f.parent_id == parent_id:
            children = _build_tree(folders, f.id)
            result.append(FolderOut(
                id=f.id, name=f.name, parent_id=f.parent_id,
                project_id=f.project_id, count=f.count, children=children,
            ))
    return result


@router.get("/folders", response_model=List[FolderOut])
def get_folders(db: Session = Depends(get_db)):
    folders = db.query(models.Folder).all()
    return _build_tree(folders)


@router.post("/folders", response_model=FolderOut, status_code=201)
def create_folder(payload: FolderCreate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    if db.query(models.Folder).filter(models.Folder.id == payload.id).first():
        raise HTTPException(status_code=409, detail="Folder ID already exists")
    folder = models.Folder(
        id=payload.id,
        name=payload.name,
        parent_id=payload.parent_id,
        project_id=payload.project_id,
        count=0,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return FolderOut(
        id=folder.id, name=folder.name, parent_id=folder.parent_id,
        project_id=folder.project_id, count=folder.count, children=[],
    )


@router.patch("/folders/{folder_id}", response_model=FolderOut)
def update_folder(folder_id: str, payload: FolderUpdate, db: Session = Depends(get_db), _: models.User = WRITE_ROLES):
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(folder, field, value)
    db.commit()
    db.refresh(folder)
    return FolderOut(
        id=folder.id, name=folder.name, parent_id=folder.parent_id,
        project_id=folder.project_id, count=folder.count, children=[],
    )


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, db: Session = Depends(get_db), _: models.User = ADMIN_ONLY):
    folder = db.query(models.Folder).filter(models.Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    child_count = db.query(models.Folder).filter(models.Folder.parent_id == folder_id).count()
    test_count = db.query(models.Test).filter(models.Test.folder_id == folder_id).count()
    if child_count > 0 or test_count > 0:
        raise HTTPException(status_code=409, detail=f"Folder has {child_count} sub-folders and {test_count} tests — move or delete them first")
    db.delete(folder)
    db.commit()
