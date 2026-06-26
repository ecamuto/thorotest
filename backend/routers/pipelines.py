from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import PipelineOut
from ..auth_utils import get_current_user

router = APIRouter(tags=["pipelines"])


@router.get("/pipelines", response_model=List[PipelineOut])
def list_pipelines(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    return db.query(models.Pipeline).all()
