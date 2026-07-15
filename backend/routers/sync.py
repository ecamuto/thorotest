"""CLI-facing sync endpoint: upsert YAML "tests as code" files pushed by the
thorotest CLI (`thorotest sync`).

Reuses the same parse/upsert pipeline as the GitHub/GitLab repo sync
(:func:`backend.github_sync.sync_repo`) via its injectable fetcher, so CLI
pushes and repo syncs behave identically: match by YAML `id` first, then by
(source, path); `status:` in the file is never applied — a test's status is
owned by real run results.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List

from ..db import get_db
from .. import models
from ..auth_utils import require_role
from ..github_sync import sync_repo

router = APIRouter(tags=["sync"])

WRITE_ROLES = require_role("admin", "manager", "tester")

# Guards against a runaway client posting an unbounded payload; a real test
# suite pushed from a working tree stays far below both limits.
MAX_FILES = 500
MAX_FILE_BYTES = 256 * 1024

DEFAULT_SOURCE = "cli://local"


class SyncFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str


class SyncYamlIn(BaseModel):
    files: List[SyncFile] = Field(min_length=1, max_length=MAX_FILES)
    ref: str = Field(default="cli", max_length=100)
    source: str = Field(default=DEFAULT_SOURCE, max_length=500)
    dry_run: bool = False


@router.post("/sync/yaml")
def sync_yaml(payload: SyncYamlIn, db: Session = Depends(get_db),
              _: models.User = WRITE_ROLES):
    for f in payload.files:
        if len(f.content.encode("utf-8", errors="replace")) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"{f.path}: file exceeds {MAX_FILE_BYTES} bytes")
    if not payload.source.startswith("cli://"):
        raise HTTPException(status_code=422, detail="source must start with 'cli://'")

    seen: set[str] = set()
    for f in payload.files:
        if f.path in seen:
            raise HTTPException(status_code=422, detail=f"duplicate path in payload: {f.path}")
        seen.add(f.path)

    def fetcher(_repo_url, _branch, _path, _token):
        return payload.ref, [(f.path, f.content) for f in payload.files]

    stats = sync_repo(db, repo_url=payload.source, branch="", path="",
                      fetcher=fetcher, commit=not payload.dry_run)
    if payload.dry_run:
        db.rollback()
    return {**stats, "dry_run": payload.dry_run}
