import csv
import io
from .base import ImportResult, TestData

# Priority normalisation
_PRIORITY_MAP = {
    "critical": "critical", "blocker": "critical",
    "high": "high", "major": "high",
    "medium": "med", "med": "med", "normal": "med",
    "low": "low", "minor": "low", "trivial": "low",
    # TestRail numeric priority IDs
    "1": "low", "2": "med", "3": "high", "4": "critical",
}

# Type normalisation
_TYPE_MAP = {
    "automated": "automated", "automatic": "automated", "auto": "automated",
    "manual": "manual",
    "1": "automated",   # TestRail type_id 1 = Automated
}


def _normalise_priority(v: str) -> str:
    return _PRIORITY_MAP.get(v.strip().lower(), "med")


def _normalise_type(v: str) -> str:
    return _TYPE_MAP.get(v.strip().lower(), "manual")


# Column alias tables: canonical_name → list of source column headers (case-insensitive)
_COLUMN_ALIASES = {
    "title":       ["title", "name", "test name", "case name", "summary"],
    "folder_path": ["section", "folder", "suite", "component", "area path", "folder path", "section hierarchy"],
    "type":        ["type", "type_id", "test type", "automated test name"],
    "status":      ["status", "state", "result"],
    "priority":    ["priority", "priority_id", "severity"],
    "owner":       ["owner", "assigned to", "assignee"],
    "tags":        ["tags", "labels", "keywords", "categories"],
    "source_id":   ["id", "test id", "case id", "work item id"],
}


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Return mapping canonical_name → actual_header for detected columns."""
    lower_headers = {h.strip().lower(): h for h in headers}
    mapping = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_headers:
                mapping[canonical] = lower_headers[alias]
                break
    return mapping


def _detect_tool(headers: list[str]) -> str:
    lower = {h.strip().lower() for h in headers}
    if "section" in lower or "section hierarchy" in lower:
        return "testrail"
    if "component" in lower or "sprint" in lower:
        return "zephyr"
    if "work item type" in lower or "area path" in lower:
        return "azure"
    return "generic"


def parse_csv(content: bytes, column_mapping: dict | None = None) -> ImportResult:
    """
    Parse a CSV export from TestRail, Zephyr Scale, Azure Test Plans, or generic CSV.
    column_mapping: optional override {canonical_name: actual_header}.
    """
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []

    auto_mapping = _detect_columns(headers)
    mapping = {**auto_mapping, **(column_mapping or {})}

    tool = _detect_tool(headers)
    tests: list[TestData] = []
    warnings: list[str] = []

    if "title" not in mapping:
        warnings.append("No title column detected — cannot import test cases from this CSV")
        return ImportResult(format_detected=f"csv ({tool})", warnings=warnings,
                            source_provider=tool)

    for row in reader:
        title = row.get(mapping["title"], "").strip()
        if not title:
            continue

        folder_path = ""
        if "folder_path" in mapping:
            folder_path = row.get(mapping["folder_path"], "").strip()
            # Azure uses " > " separator, TestRail uses " / " — normalise to "/"
            folder_path = folder_path.replace(" > ", "/").strip("/")

        raw_priority = row.get(mapping.get("priority", ""), "").strip()
        raw_type = row.get(mapping.get("type", ""), "").strip()

        raw_tags = row.get(mapping.get("tags", ""), "").strip()
        tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()] if raw_tags else []

        tests.append(TestData(
            title=title,
            folder_path=folder_path,
            type=_normalise_type(raw_type) if raw_type else "manual",
            status="pending",
            priority=_normalise_priority(raw_priority) if raw_priority else "med",
            owner=row.get(mapping.get("owner", ""), "").strip(),
            tags=tags,
            source_id=row.get(mapping.get("source_id", ""), "").strip(),
        ))

    return ImportResult(
        tests=tests,
        format_detected=f"csv ({tool})",
        warnings=warnings,
        source_provider=tool,
    )


def get_csv_columns(content: bytes) -> dict:
    """Return detected headers and column mapping for UI display."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    mapping = _detect_columns(headers)
    tool = _detect_tool(headers)
    return {"headers": headers, "mapping": mapping, "tool": tool}
