import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from ..db import get_db
from .. import models
from ..importers import (
    detect_format, parse_csv, parse_testrail_xml, parse_testlink_xml,
    parse_junit_xml, parse_json,
    parse_zephyr, parse_xray, parse_qtest, ImportResult,
)
from ..importers.csv_importer import get_csv_columns, get_xlsx_columns
from ..importers import parse_xlsx
from ..importers.persist import persist_import_result
from ..auth_utils import require_role

router = APIRouter(tags=["import"])

# Importing creates folders/tests/runs — same write roles as manual creation.
WRITE_ROLES = require_role("admin", "manager", "tester")

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _run_parser(fmt: str, content: bytes, column_mapping: dict | None) -> ImportResult:
    if fmt == "csv":
        return parse_csv(content, column_mapping)
    if fmt == "xlsx":
        return parse_xlsx(content, column_mapping)
    if fmt == "testrail_xml":
        return parse_testrail_xml(content)
    if fmt == "testlink_xml":
        return parse_testlink_xml(content)
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
    "testlink_xml": "testlink",
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
    elif fmt == "xlsx":
        result["csv_meta"] = get_xlsx_columns(content)

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

    stats = persist_import_result(db, result, provider, conflict)

    return {
        "ok": True,
        "format": fmt,
        "imported": stats,
        "warnings": result.warnings,
    }
