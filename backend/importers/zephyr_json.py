"""Zephyr Scale (Adaptavist / SmartBear TM4J) JSON importer.

Handles the JSON produced by the Zephyr Scale REST API (`GET /testcases`,
`GET /testexecutions`) and the native "Export → JSON" action, which wrap
records in a top-level ``{"values": [...], "isLast": ..., "total": ...}``
envelope. Fields come in two shapes depending on API version / export path:

  * scalar:  ``"priority": "High"``, ``"status": "Approved"``
  * object:  ``"priority": {"name": "High"}``, ``"folder": {"fullName": "/A/B"}``

Both are accepted. Test cases become TestData; test executions (when present)
are grouped by cycle into RunData with per-case results.
"""
import json
from datetime import datetime
from .base import ImportResult, TestData, RunData, CaseResult

# Zephyr Scale default priority scheme is High / Normal / Low; Critical and
# Blocker show up on customised schemes.
_PRIORITY_MAP = {
    "critical": "critical", "blocker": "critical", "highest": "critical",
    "high": "high", "major": "high",
    "normal": "med", "medium": "med", "med": "med",
    "low": "low", "minor": "low", "trivial": "low", "lowest": "low",
}

# Execution result statuses. Lifecycle statuses (Draft/Approved/Deprecated)
# are NOT run results and are deliberately left out — test cases stay "pending".
_STATUS_MAP = {
    "pass": "pass", "passed": "pass",
    "fail": "fail", "failed": "fail",
    "blocked": "blocked", "block": "blocked",
    "not executed": "pending", "unexecuted": "pending", "not run": "pending",
    "in progress": "pending", "wip": "pending", "pending": "pending",
}


def _text(v) -> str:
    """Coerce a scalar-or-object Zephyr field into a display string."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for key in ("fullName", "name", "displayName", "key", "value"):
            if v.get(key):
                return str(v[key]).strip()
        return ""
    return str(v).strip()


def _norm_priority(v) -> str:
    return _PRIORITY_MAP.get(_text(v).lower(), "med")


def _norm_status(v) -> str:
    return _STATUS_MAP.get(_text(v).lower(), "pending")


def _folder_path(item: dict) -> str:
    """Extract a '/'-joined folder path, tolerating several field names."""
    raw = (
        item.get("folder")
        or item.get("folderName")
        or item.get("folderId")   # only a name if the export inlined it
        or item.get("component")
    )
    path = _text(raw)
    # Zephyr folder full names are like "/Login/OAuth" — strip leading slash.
    return path.strip("/")


def _labels(item: dict) -> list:
    raw = item.get("labels") or item.get("tags") or []
    if isinstance(raw, str):
        return [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]
    if isinstance(raw, list):
        return [_text(t) for t in raw if _text(t)]
    return []


def _is_execution(item: dict) -> bool:
    """A test-execution record references a test case rather than being one."""
    return "testCase" in item or "testCaseKey" in item or "testCycle" in item


def _test_case_key(item: dict) -> str:
    """The test case a record points at (for executions) or its own key."""
    tc = item.get("testCase")
    if isinstance(tc, dict):
        return _text(tc.get("key") or tc.get("name"))
    return _text(item.get("testCaseKey") or tc or item.get("key"))


def parse_zephyr(content: bytes) -> ImportResult:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return ImportResult(warnings=[f"JSON parse error: {e}"], format_detected="zephyr")

    # Accept the {"values": [...]} envelope or a bare array of records.
    if isinstance(data, dict):
        records = data.get("values") or data.get("testCases") or data.get("data") or []
    elif isinstance(data, list):
        records = data
    else:
        records = []

    if not isinstance(records, list) or not records:
        return ImportResult(
            warnings=["No Zephyr records found (expected a 'values' array)"],
            format_detected="zephyr",
        )

    tests: list[TestData] = []
    warnings: list[str] = []
    # Map source key -> title so executions can resolve their test title.
    key_to_title: dict[str, str] = {}
    # cycle identity (key or name) -> {"name": str, "cases": list[CaseResult]}
    cycles: dict[str, dict] = {}

    for item in records:
        if not isinstance(item, dict):
            continue

        if _is_execution(item):
            tc_key = _test_case_key(item)
            title = key_to_title.get(tc_key, "")
            if not title:
                # Execution may precede its case, or the case isn't in this
                # export — fall back to the referenced name if available.
                tc = item.get("testCase")
                title = _text(tc.get("name")) if isinstance(tc, dict) else ""
            if not title:
                warnings.append(f"Execution for unknown test case '{tc_key}' skipped")
                continue
            cycle_name = _text(item.get("testCycle")) or _text(item.get("testCycleKey")) \
                or f"Zephyr Import {datetime.now().strftime('%Y-%m-%d')}"
            # Prefer the cycle key as the dedup id; fall back to its name.
            tcyc = item.get("testCycle")
            cycle_key = (_text(tcyc.get("key")) if isinstance(tcyc, dict) else "") \
                or _text(item.get("testCycleKey")) or cycle_name
            cyc = cycles.setdefault(cycle_key, {"name": cycle_name, "cases": []})
            cyc["cases"].append(
                CaseResult(test_title=title, status=_norm_status(item.get("status")),
                           source_test_id=tc_key)
            )
            continue

        # Test case record
        title = _text(item.get("name") or item.get("title") or item.get("summary"))
        if not title:
            warnings.append(f"Skipped test case with no name (key={_text(item.get('key'))})")
            continue

        key = _text(item.get("key"))
        if key:
            key_to_title[key] = title

        # A testScript with steps means a manual case; automation is flagged
        # via customFields or an "automated" marker in some exports.
        automated = bool(item.get("automated")) or _text(item.get("testType")).lower() == "automated"

        tests.append(TestData(
            title=title,
            folder_path=_folder_path(item),
            type="automated" if automated else "manual",
            status="pending",
            priority=_norm_priority(item.get("priority") or item.get("priorityName")),
            owner=_text(item.get("owner") or item.get("ownerName") or item.get("assignedTo")),
            tags=_labels(item),
            source_id=key,
        ))

    runs = [
        RunData(name=cyc["name"], status="done", cases=cyc["cases"],
                source_id=cycle_key if cycle_key != cyc["name"] else "")
        for cycle_key, cyc in cycles.items()
        if cyc["cases"]
    ]

    return ImportResult(
        tests=tests,
        runs=runs,
        warnings=warnings,
        format_detected="zephyr (json)",
        source_provider="zephyr",
    )
