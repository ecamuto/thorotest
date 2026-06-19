import json
from datetime import datetime
from .base import ImportResult, TestData, RunData, DefectData, CaseResult

_PRIORITY_MAP = {
    "critical": "critical", "blocker": "critical",
    "high": "high", "major": "high",
    "medium": "med", "med": "med", "normal": "med",
    "low": "low", "minor": "low", "trivial": "low",
}

_STATUS_MAP = {
    "passed": "pass", "pass": "pass",
    "failed": "fail", "fail": "fail", "broken": "fail",
    "skipped": "blocked", "blocked": "blocked",
    "pending": "pending",
}


def _norm_priority(v: str) -> str:
    return _PRIORITY_MAP.get(str(v).lower(), "med")


def _norm_status(v: str) -> str:
    return _STATUS_MAP.get(str(v).lower(), "pending")


def _parse_allure(data: list) -> ImportResult:
    """Parse Allure JSON results array."""
    tests: list[TestData] = []
    cases: list[CaseResult] = []
    warnings: list[str] = []

    for item in data:
        title = item.get("name") or item.get("fullName", "")
        if not title:
            continue

        # Extract suite label as folder
        folder_path = ""
        for label in item.get("labels", []):
            if label.get("name") == "suite":
                folder_path = label.get("value", "")
            elif label.get("name") == "parentSuite" and not folder_path:
                folder_path = label.get("value", "")

        status = _norm_status(item.get("status", ""))

        tests.append(TestData(
            title=title,
            folder_path=folder_path,
            type="automated",
            status="pending",
        ))
        cases.append(CaseResult(test_title=title, status=status))

    run = RunData(
        name=f"Allure Import {datetime.now().strftime('%Y-%m-%d')}",
        status="done",
        cases=cases,
    )

    return ImportResult(
        tests=tests,
        runs=[run] if cases else [],
        warnings=warnings,
        format_detected="json (allure)",
    )


def _parse_generic(data: dict) -> ImportResult:
    """Parse generic JSON with optional tests/runs/defects keys."""
    tests: list[TestData] = []
    runs: list[RunData] = []
    defects: list[DefectData] = []
    warnings: list[str] = []

    for item in data.get("tests", []):
        title = item.get("title") or item.get("name", "")
        if not title:
            continue
        tests.append(TestData(
            title=title,
            folder_path=item.get("folder") or item.get("section") or item.get("suite", ""),
            type=item.get("type", "manual"),
            status=item.get("status", "pending"),
            priority=_norm_priority(item.get("priority", "med")),
            owner=item.get("owner", ""),
            tags=item.get("tags", []),
            source_id=str(item.get("id", "")),
        ))

    for item in data.get("runs", []):
        name = item.get("name") or item.get("title", "")
        if not name:
            continue
        raw_cases = item.get("cases", item.get("results", []))
        cases = [
            CaseResult(
                test_title=c.get("title") or c.get("name", ""),
                status=_norm_status(c.get("status", "pending")),
            )
            for c in raw_cases
        ]
        runs.append(RunData(name=name, status=item.get("status", "done"), cases=cases))

    for item in data.get("defects", []):
        title = item.get("title") or item.get("name", "")
        if not title:
            continue
        defects.append(DefectData(
            title=title,
            status=item.get("status", "open"),
            severity=_norm_priority(item.get("severity", "med")),
            description=item.get("description", ""),
            test_title=item.get("test_title", ""),
            source_id=str(item.get("id", "")),
        ))

    return ImportResult(
        tests=tests,
        runs=runs,
        defects=defects,
        warnings=warnings,
        format_detected="json (generic)",
    )


def parse_json(content: bytes) -> ImportResult:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return ImportResult(warnings=[f"JSON parse error: {e}"], format_detected="json")

    # Allure format: root is a list of test result objects
    if isinstance(data, list) and data and isinstance(data[0], dict) and "status" in data[0]:
        return _parse_allure(data)

    if isinstance(data, dict):
        return _parse_generic(data)

    return ImportResult(
        warnings=["Unrecognised JSON structure — expected object with 'tests' key or Allure array"],
        format_detected="json",
    )
