"""Activity feed writer used by mutation endpoints.

Adds a row to the `activity` table inside the caller's session so it commits
atomically with the mutation itself — callers invoke this right before their
own db.commit().
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models


def actor_name(user: models.User) -> str:
    return user.display_name or user.username


def log_activity(db: Session, who: str, what: str, target: str, detail: str = "") -> None:
    db.add(models.Activity(
        who=who,
        what=what,
        target=target,
        detail=detail,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))
