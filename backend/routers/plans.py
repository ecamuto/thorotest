import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from ..db import get_db
from .. import models
from ..schemas import PlanOut, PlanCreate, RunOut
from ..auth_utils import require_role, get_current_user
from ..activity_utils import log_activity, actor_name
from ..audit_utils import log_event, EVT_RUN_STARTED
from ._pagination import paginate, MAX_LIMIT

router = APIRouter(tags=["plans"])

WRITE_ROLES = require_role("admin", "manager", "tester")


@router.get("/plans", response_model=List[PlanOut])
def list_plans(
    response: Response,
    limit: int = MAX_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return paginate(
        db.query(models.TestPlan).order_by(models.TestPlan.created_at.desc()),
        response, limit, offset,
    )


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    # Keep only test ids that exist, preserving order and dropping dups.
    seen: set[str] = set()
    valid_ids: list[str] = []
    for tid in payload.test_ids:
        if tid in seen:
            continue
        if db.query(models.Test.id).filter(models.Test.id == tid).first():
            valid_ids.append(tid)
            seen.add(tid)

    plan = models.TestPlan(
        id=f"PLAN-{uuid.uuid4().hex[:6].upper()}",
        name=payload.name,
        env=payload.env,
        owner=actor_name(current_user),
        schedule=payload.schedule or "Manual",
        test_ids=valid_ids,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    db.add(plan)
    log_activity(db, actor_name(current_user), "created plan", plan.id, plan.name)
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: str, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    plan = db.query(models.TestPlan).filter(models.TestPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    db.delete(plan)
    log_activity(db, actor_name(current_user), "deleted plan", plan.id, plan.name)
    db.commit()
    return Response(status_code=204)


@router.post("/plans/{plan_id}/run", response_model=RunOut, status_code=201)
def run_plan(plan_id: str, db: Session = Depends(get_db), current_user: models.User = WRITE_ROLES):
    """Instantiate a run from a plan's tests. Cases start `pending`; results are
    recorded manually or via CI import — ThoroTest tracks, it does not execute."""
    plan = db.query(models.TestPlan).filter(models.TestPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    test_ids = plan.test_ids or []
    if not test_ids:
        raise HTTPException(status_code=400, detail="Plan has no tests")

    now = datetime.now(timezone.utc).isoformat()
    rid = f"R-{uuid.uuid4().hex[:6].upper()}"
    run = models.Run(
        id=rid,
        name=plan.name,
        status="pending",
        total=len(test_ids),
        owner=actor_name(current_user),
        env=plan.env,
        started="just now",
        created_at=now,
    )
    db.add(run)
    db.flush()
    for tid in test_ids:
        db.add(models.RunCase(run_id=rid, test_id=tid, status="pending"))

    log_activity(db, actor_name(current_user), "started run", run.id, run.name)
    db.commit()
    db.refresh(run)
    log_event(
        EVT_RUN_STARTED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        description=f"{current_user.email} ran plan '{plan.name}'",
        target_type="run",
        target_id=str(run.id),
    )
    return run
