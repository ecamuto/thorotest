import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from ..db import get_db
from .. import models
from ..importers import (
    detect_format, parse_csv, parse_testrail_xml, parse_junit_xml, parse_json,
    parse_zephyr, parse_xray, parse_qtest, ImportResult,
)
from ..importers.csv_importer import get_csv_columns
from ..auth_utils import require_role

router = APIRouter(tags=["import"])

# Importing creates folders/tests/runs — same write roles as manual creation.
WRITE_ROLES = require_role("admin", "manager", "tester")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _run_parser(fmt: str, content: bytes, column_mapping: dict | None) -> ImportResult:
    if fmt == "csv":
        return parse_csv(content, column_mapping)
    if fmt == "testrail_xml":
        return parse_testrail_xml(content)
    if fmt == "junit_xml":
        return parse_junit_xml(content)
    if fmt == "json":
        return parse_json(content)
    if fmt == "zephyr":
        return parse_zephyr(content)
    if fmt == "xray":
        return parse_xray(content)
    if fmt == "qtest":
        return parse_qtest(content)
    raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")


# Fallback provider token when a parser doesn't set ImportResult.source_provider.
_FMT_PROVIDER = {
    "zephyr": "zephyr",
    "xray": "xray",
    "qtest": "qtest",
    "testrail_xml": "testrail",
    "junit_xml": "junit",
    "csv": "csv",
    "json": "json",
}


def _provider_for(fmt: str, result: ImportResult) -> str:
    """Normalised source-tool name used as Test/Defect external_provider."""
    return result.source_provider or _FMT_PROVIDER.get(fmt, fmt)


@router.post("/import/detect")
async def detect_file(file: UploadFile = File(...), _: models.User = WRITE_ROLES):
    """Return detected format and (for CSV) the column headers for mapping UI."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    fmt = detect_format(file.filename or "", content)
    result = {"format": fmt, "filename": file.filename}

    if fmt == "csv":
        result["csv_meta"] = get_csv_columns(content)

    return result


@router.post("/import/preview")
async def preview_import(
    file: UploadFile = File(...),
    format: Optional[str] = Form(None),
    column_mapping: Optional[str] = Form(None),
    _: models.User = WRITE_ROLES,
):
    """Parse file and return summary + sample rows without writing to DB."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    fmt = format or detect_format(file.filename or "", content)

    mapping = None
    if column_mapping:
        import json
        try:
            mapping = json.loads(column_mapping)
        except Exception:
            raise HTTPException(status_code=400, detail="column_mapping must be valid JSON")

    result = _run_parser(fmt, content, mapping)
    summary = result.summary()

    # Include first 5 tests as preview sample
    sample_tests = [
        {
            "title": t.title,
            "folder_path": t.folder_path,
            "type": t.type,
            "priority": t.priority,
            "tags": t.tags,
        }
        for t in result.tests[:5]
    ]

    sample_runs = [
        {"name": r.name, "cases": len(r.cases)}
        for r in result.runs[:3]
    ]

    return {**summary, "sample_tests": sample_tests, "sample_runs": sample_runs}


@router.post("/import/execute")
async def execute_import(
    file: UploadFile = File(...),
    format: Optional[str] = Form(None),
    column_mapping: Optional[str] = Form(None),
    conflict: str = Form("skip"),   # skip | overwrite | rename
    db: Session = Depends(get_db),
    _: models.User = WRITE_ROLES,
):
    """Parse file and persist data to DB."""
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    fmt = format or detect_format(file.filename or "", content)

    mapping = None
    if column_mapping:
        import json
        try:
            mapping = json.loads(column_mapping)
        except Exception:
            raise HTTPException(status_code=400, detail="column_mapping must be valid JSON")

    result = _run_parser(fmt, content, mapping)
    provider = _provider_for(fmt, result)

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

    return {
        "ok": True,
        "format": fmt,
        "imported": stats,
        "warnings": result.warnings,
    }
