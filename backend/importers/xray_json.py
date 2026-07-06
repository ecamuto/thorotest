"""Xray (Jira test management) JSON importer.

Handles the two JSON shapes Xray produces:

  1. Test definitions — an array of test objects using Xray's bulk test
     import schema::

        [{"testtype": "Manual",
          "xray_test_repository_folder": "/Login/OAuth",
          "fields": {"summary": "...", "priority": {"name": "High"},
                     "labels": ["smoke"]},
          "key": "PROJ-123"}]

  2. Execution results — the Xray JSON results format::

        {"info": {"summary": "Regression run", "testExecutionKey": "PROJ-42"},
         "tests": [{"testKey": "PROJ-123", "status": "PASS"}]}

Definitions become tests; execution results become a single run whose cases
link to tests by their Xray issue key.
"""
import json
from datetime import datetime
from .base import ImportResult, TestData, RunData, CaseResult

_PRIORITY_MAP = {
    "critical": "critical", "blocker": "critical", "highest": "critical",
    "high": "high", "major": "high",
    "medium": "med", "normal": "med", "med": "med",
    "low": "low", "minor": "low", "trivial": "low", "lowest": "low",
}

# Xray execution statuses.
_STATUS_MAP = {
    "pass": "pass", "passed": "pass",
    "fail": "fail", "failed": "fail",
    "aborted": "blocked", "blocked": "blocked",
    "todo": "pending", "executing": "pending", "pending": "pending",
}

_AUTOMATED_TYPES = {"automated", "cucumber", "generic"}


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for key in ("name", "value", "key", "displayName"):
            if v.get(key):
                return str(v[key]).strip()
        return ""
    return str(v).strip()


def _norm_priority(v) -> str:
    return _PRIORITY_MAP.get(_text(v).lower(), "med")


def _norm_status(v) -> str:
    return _STATUS_MAP.get(_text(v).lower(), "pending")


def _labels(fields: dict) -> list:
    raw = fields.get("labels") or fields.get("tags") or []
    if isinstance(raw, str):
        return [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]
    if isinstance(raw, list):
        return [_text(t) for t in raw if _text(t)]
    return []


def _parse_test_def(item: dict, tests: list, key_to_title: dict, warnings: list):
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    title = _text(fields.get("summary") or item.get("summary") or item.get("name"))
    if not title:
        warnings.append(f"Skipped Xray test with no summary (key={_text(item.get('key'))})")
        return

    key = _text(item.get("key") or item.get("testKey"))
    if key:
        key_to_title[key] = title

    testtype = _text(item.get("testtype") or item.get("testType"))
    folder = _text(item.get("xray_test_repository_folder")
                   or item.get("testRepositoryPath")
                   or fields.get("components")).strip("/")

    tests.append(TestData(
        title=title,
        folder_path=folder,
        type="automated" if testtype.lower() in _AUTOMATED_TYPES else "manual",
        status="pending",
        priority=_norm_priority(fields.get("priority")),
        owner=_text(fields.get("assignee") or fields.get("reporter")),
        tags=_labels(fields),
        source_id=key,
    ))


def parse_xray(content: bytes) -> ImportResult:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return ImportResult(warnings=[f"JSON parse error: {e}"], format_detected="xray")

    tests: list[TestData] = []
    runs: list[RunData] = []
    warnings: list[str] = []
    key_to_title: dict[str, str] = {}

    # Test definitions: a bare array of test objects.
    definitions = data if isinstance(data, list) else data.get("tests") if isinstance(data, dict) else None

    # An execution-results object has an "info" block and result-shaped
    # entries ("testKey"/"status") rather than definition-shaped ones.
    is_results = (
        isinstance(data, dict)
        and isinstance(data.get("tests"), list)
        and any(isinstance(t, dict) and ("testKey" in t or "status" in t)
                and "fields" not in t for t in data["tests"])
    )

    if is_results:
        info = data.get("info") or {}
        run_name = _text(info.get("summary")) or f"Xray Import {datetime.now().strftime('%Y-%m-%d')}"
        run_key = _text(info.get("testExecutionKey") or data.get("testExecutionKey"))
        cases = []
        for t in data["tests"]:
            if not isinstance(t, dict):
                continue
            tc_key = _text(t.get("testKey") or t.get("key"))
            if not tc_key:
                continue
            cases.append(CaseResult(
                test_title=key_to_title.get(tc_key, ""),
                status=_norm_status(t.get("status")),
                source_test_id=tc_key,
            ))
        if cases:
            runs.append(RunData(name=run_name, status="done", cases=cases,
                                source_id=run_key))
    elif isinstance(definitions, list):
        for item in definitions:
            if isinstance(item, dict):
                _parse_test_def(item, tests, key_to_title, warnings)
    else:
        warnings.append("Unrecognised Xray JSON — expected a test array or a results object")

    return ImportResult(
        tests=tests,
        runs=runs,
        warnings=warnings,
        format_detected="xray (json)",
        source_provider="xray",
    )
