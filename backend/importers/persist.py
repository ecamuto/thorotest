"""Persist a parsed ImportResult into the DB.

Shared by the file-import endpoint (`/api/import/execute`) and the GitHub
Actions collector, so both use the same folder-tree building, external-identity
matching/dedup, and run/defect linking.
"""
import uuid
from datetime import datetime, timezone

from .. import models
from .base import ImportResult


def persist_import_result(db, result: ImportResult, provider: str, conflict: str = "skip",
                          sync_status: bool = False) -> dict:
    """Write tests/runs/defects from `result`. `conflict` = skip | overwrite |
    rename. Returns a stats dict. Commits the session.

    When `sync_status` is True, each test a run case links to has its own
    `status` advanced to that case's result — so a real CI run updates the
    test's current status (last case wins). Off by default: file imports of a
    plain results file shouldn't silently rewrite test statuses; the CI
    collectors opt in so a pipeline result is the source of truth for status."""
    now = datetime.now(timezone.utc).isoformat()
    stats = {"folders": 0, "tests": 0, "runs": 0, "defects": 0, "skipped": 0}

    # ── Folders ────────────────────────────────────────────────
    folder_cache: dict[str, str] = {}  # path → folder.id

    def _get_or_create_folder(path: str) -> str:
        if not path:
            return ""
        if path in folder_cache:
            return folder_cache[path]

        parts = [p.strip() for p in path.split("/") if p.strip()]
        parent_id = None
        current_path = ""

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            if current_path in folder_cache:
                parent_id = folder_cache[current_path]
                continue

            existing = db.query(models.Folder).filter(
                models.Folder.name == part,
                models.Folder.parent_id == parent_id,
            ).first()

            if existing:
                folder_cache[current_path] = existing.id
                parent_id = existing.id
            else:
                fid = f"F-{uuid.uuid4().hex[:8].upper()}"
                folder = models.Folder(id=fid, name=part, parent_id=parent_id)
                db.add(folder)
                db.flush()
                folder_cache[current_path] = fid
                parent_id = fid
                stats["folders"] += 1

        return folder_cache[path]

    # ── Tests ──────────────────────────────────────────────────
    title_to_id: dict[str, str] = {}       # title → test.id (fallback linking)
    key_to_id: dict[str, str] = {}         # source_id → test.id (primary linking)

    for t in result.tests:
        folder_id = _get_or_create_folder(t.folder_path) if t.folder_path else None

        # Match order: stable external identity (provider, key) first, so
        # re-imports update the same test and same-title cases in different
        # folders stay distinct. Fall back to (title, folder) for sources with
        # no key. Title-only matching is deliberately avoided.
        existing = None
        if t.source_id:
            existing = db.query(models.Test).filter(
                models.Test.external_provider == provider,
                models.Test.external_key == t.source_id,
            ).first()
        if existing is None:
            existing = db.query(models.Test).filter(
                models.Test.title == t.title,
                models.Test.folder_id == folder_id,
            ).first()

        if existing:
            if conflict == "skip":
                title_to_id[t.title] = existing.id
                if t.source_id:
                    key_to_id[t.source_id] = existing.id
                stats["skipped"] += 1
                continue
            elif conflict == "overwrite":
                existing.folder_id = folder_id
                existing.type = t.type
                existing.priority = t.priority
                existing.tags = t.tags
                existing.owner = t.owner or existing.owner
                existing.updated_at = now
                # Backfill external identity if this test was matched by title.
                if t.source_id and not existing.external_key:
                    existing.external_provider = provider
                    existing.external_key = t.source_id
                title_to_id[t.title] = existing.id
                if t.source_id:
                    key_to_id[t.source_id] = existing.id
                db.flush()
                stats["tests"] += 1
                continue
            elif conflict == "rename":
                t.title = f"{t.title} (imported)"

        tid = f"TC-{uuid.uuid4().hex[:6].upper()}"
        test = models.Test(
            id=tid,
            title=t.title,
            folder_id=folder_id,
            type=t.type,
            status=t.status,
            priority=t.priority,
            owner=t.owner or "",
            tags=t.tags,
            auto=t.type == "automated",
            updated_at=now,
            external_provider=provider if t.source_id else None,
            external_key=t.source_id or None,
        )
        db.add(test)
        db.flush()
        title_to_id[t.title] = tid
        if t.source_id:
            key_to_id[t.source_id] = tid
        stats["tests"] += 1

    def _resolve_test_id(source_test_id: str, test_title: str) -> str | None:
        """Link a case to a test by source id first, then title. Source ids
        also resolve against tests imported in a previous run (same provider),
        so a results-only file links to earlier-imported test definitions."""
        if source_test_id:
            if source_test_id in key_to_id:
                return key_to_id[source_test_id]
            prior = db.query(models.Test).filter(
                models.Test.external_provider == provider,
                models.Test.external_key == source_test_id,
            ).first()
            if prior is not None:
                key_to_id[source_test_id] = prior.id  # cache for the rest of this run
                return prior.id
        return title_to_id.get(test_title)

    # ── Runs ──────────────────────────────────────────────────
    for run_data in result.runs:
        # Dedup: skip a run already imported from the same source cycle.
        if run_data.source_id:
            dup = db.query(models.Run).filter(
                models.Run.source_run_id == run_data.source_id,
            ).first()
            if dup is not None:
                stats["skipped"] += 1
                continue

        rid = f"R-{uuid.uuid4().hex[:6].upper()}"
        total = len(run_data.cases)
        passed = sum(1 for c in run_data.cases if c.status == "pass")
        failed = sum(1 for c in run_data.cases if c.status == "fail")
        blocked = sum(1 for c in run_data.cases if c.status == "blocked")

        run = models.Run(
            id=rid,
            name=run_data.name,
            status=run_data.status,
            total=total,
            passed=passed,
            failed=failed,
            blocked=blocked,
            progress=100 if total > 0 else 0,
            started=now,
            source_run_id=run_data.source_id or None,
        )
        db.add(run)
        db.flush()

        for case in run_data.cases:
            test_id = _resolve_test_id(case.source_test_id, case.test_title)
            if not test_id:
                continue
            db.add(models.RunCase(run_id=rid, test_id=test_id, status=case.status))
            if sync_status:
                linked = db.query(models.Test).filter(models.Test.id == test_id).first()
                if linked is not None:
                    linked.status = case.status
                    linked.last_run_at = now

        stats["runs"] += 1

    # ── Defects ───────────────────────────────────────────────
    for d in result.defects:
        # Dedup: skip a defect already imported from the same source key.
        if d.source_id:
            dup = db.query(models.Defect).filter(
                models.Defect.external_provider == provider,
                models.Defect.external_key == d.source_id,
            ).first()
            if dup is not None:
                stats["skipped"] += 1
                continue

        did = f"D-{uuid.uuid4().hex[:6].upper()}"
        # DefectData carries no source_test_id, so link by title only.
        test_id = title_to_id.get(d.test_title) if d.test_title else None
        defect = models.Defect(
            id=did,
            title=d.title,
            status=d.status,
            severity=d.severity,
            description=d.description,
            test_id=test_id,
            created_at=now,
            external_provider=provider if d.source_id else None,
            external_key=d.source_id or None,
        )
        db.add(defect)
        stats["defects"] += 1

    db.commit()
    return stats
