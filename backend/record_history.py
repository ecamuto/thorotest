"""record_history.py — per-record field-level change tracking.

Writes into the caller's session so the history row commits atomically with the
mutation itself (same pattern as activity_utils.log_activity). For updates the
caller invokes log_update *before* applying setattr, so the object still holds
the old values and `data` holds the incoming new values.

Usage:
    from .record_history import log_create, log_update, log_delete

    # create
    log_create(db, "test", t.id, current_user)

    # update — call before mutating the object
    log_update(db, "test", t.id, current_user, t, data)
    for field, value in data.items():
        setattr(t, field, value)

    # delete
    log_delete(db, "defect", d.id, current_user)
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models

# Machine-managed / noisy columns never worth surfacing as a user change.
_IGNORED = {
    "updated_at", "last_run_at", "duration",
    "source_ref", "source_body", "source_synced_at", "last_sync",
}


def actor_name(user: models.User) -> str:
    return user.display_name or user.username


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt(v):
    """Render a value as a JSON-safe scalar for storage/display."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def _write(db: Session, entity_type: str, entity_id, action: str, user, changes: list) -> None:
    db.add(models.RecordHistory(
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        actor_id=getattr(user, "id", None),
        actor_name=actor_name(user),
        changes=changes,
        created_at=_now(),
    ))


def log_create(db: Session, entity_type: str, entity_id, user) -> None:
    _write(db, entity_type, entity_id, "created", user, [])


def log_delete(db: Session, entity_type: str, entity_id, user) -> None:
    _write(db, entity_type, entity_id, "deleted", user, [])


def diff_fields(obj, data: dict) -> list:
    """Return the list of changed-field entries between `obj`'s current values
    and the incoming `data`. Ignores machine-managed columns."""
    changes = []
    for field, new in data.items():
        if field in _IGNORED:
            continue
        old = getattr(obj, field, None)
        if old != new:
            changes.append({"field": field, "old": _fmt(old), "new": _fmt(new)})
    return changes


def write_changes(db: Session, entity_type: str, entity_id, user, changes: list) -> None:
    """Write one 'updated' history row for a pre-computed change list. No-op when empty."""
    if changes:
        _write(db, entity_type, entity_id, "updated", user, changes)


def log_update(db: Session, entity_type: str, entity_id, user, obj, data: dict) -> None:
    """Diff incoming `data` against the object's current values and record the
    changed fields. No-op when nothing actually changed. Must be called *before*
    the caller applies the new values to `obj`."""
    write_changes(db, entity_type, entity_id, user, diff_fields(obj, data))
