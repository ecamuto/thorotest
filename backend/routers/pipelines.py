from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from typing import List
from ..db import get_db
from .. import models
from ..schemas import PipelineOut
from ..auth_utils import get_current_user
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["pipelines"])


@router.get("/pipelines", response_model=List[PipelineOut])
def list_pipelines(
    response: Response,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return paginate(db.query(models.Pipeline).order_by(models.Pipeline.id), response, limit, offset)
