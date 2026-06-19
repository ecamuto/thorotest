from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .. import models
from ..auth_utils import get_current_user

router = APIRouter(tags=["favorites"])


class FavoriteCreate(BaseModel):
    folder_id: str


@router.get("/favorites")
def list_favorites(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    favs = db.query(models.UserFavorite).filter_by(user_id=current_user.id).all()
    result = []
    for fav in favs:
        folder = db.query(models.Folder).filter_by(id=fav.folder_id).first()
        if folder:
            count = db.query(models.Test).filter_by(folder_id=folder.id).count()
            result.append({"folder_id": folder.id, "name": folder.name, "count": count})
    return result


@router.post("/favorites", status_code=201)
def add_favorite(payload: FavoriteCreate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    folder = db.query(models.Folder).filter_by(id=payload.folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    existing = db.query(models.UserFavorite).filter_by(user_id=current_user.id, folder_id=payload.folder_id).first()
    if not existing:
        db.add(models.UserFavorite(user_id=current_user.id, folder_id=payload.folder_id))
        db.commit()
    count = db.query(models.Test).filter_by(folder_id=payload.folder_id).count()
    return {"folder_id": folder.id, "name": folder.name, "count": count}


@router.delete("/favorites/{folder_id}", status_code=204)
def remove_favorite(folder_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    fav = db.query(models.UserFavorite).filter_by(user_id=current_user.id, folder_id=folder_id).first()
    if fav:
        db.delete(fav)
        db.commit()
