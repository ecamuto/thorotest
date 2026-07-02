from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import ActivityOut
from ..auth_utils import get_current_user
from ._pagination import paginate

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=List[ActivityOut])
def list_activity(
    response: Response,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return paginate(db.query(models.Activity).order_by(models.Activity.id.desc()), response, limit, offset)
