from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import ActivityOut

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=List[ActivityOut])
def list_activity(db: Session = Depends(get_db)):
    return db.query(models.Activity).order_by(models.Activity.id.desc()).all()
