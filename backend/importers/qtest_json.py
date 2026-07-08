"""qTest (Tricentis qTest Manager) JSON importer.

Handles the JSON qTest's REST API returns for test cases, either as a bare
array or wrapped in an ``{"items": [...]}`` / ``{"test-cases": [...]}``
envelope. qTest carries most attributes in a ``properties`` array of
``{"field_name": ..., "field_value": ..., "field_value_name": ...}`` entries
rather than as top-level fields::

    {"items": [
      {"pid": "TC-5", "name": "Login works", "parent_id": 10,
       "test_case_version_id": 42,
       "properties": [
         {"field_name": "Priority", "field_value_name": "High"},
         {"field_name": "Module", "field_value": "Login/OAuth"},
         {"field_name": "Automation", "field_value_name": "Yes"}]}]}

Test cases become tests; the folder path is taken from a Module/Folder
property or an inline module name. Test steps and executions are not modelled.
"""
import json
from .base import ImportResult, TestData

_PRIORITY_MAP = {
    "critical": "critical", "blocker": "critical", "urgent": "critical",
    "high": "high", "major": "high", "p1": "high",
    "medium": "med", "normal": "med", "med": "med", "p2": "med",
    "low": "low", "minor": "low", "trivial": "low", "p3": "low",
    # qTest numeric priority ids (default scheme: 1 High .. 3 Low)
    "1": "high", "2": "med", "3": "low",
}

# Property field names (lower-cased) that hold a folder/module path.
_FOLDER_FIELDS = ("module", "folder", "module path", "path")
_PRIORITY_FIELDS = ("priority",)
_OWNER_FIELDS = ("assigned to", "assignee", "owner", "created by")
_TAG_FIELDS = ("tags", "labels")
_AUTOMATION_FIELDS = ("automation", "automated", "type", "test type")


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for key in ("field_value_name", "name", "value", "field_value"):
            if v.get(key):
                return str(v[key]).strip()
        return ""
    return str(v).strip()


def _properties(item: dict) -> dict:
    """Flatten qTest's properties array into {lower field_name: display value}.

    Prefers field_value_name (the human label) over the raw field_value id."""
    out: dict[str, str] = {}
    props = item.get("properties")
    if not isinstance(props, list):
        return out
    for p in props:
        if not isinstance(p, dict):
            continue
        name = _text(p.get("field_name")).lower()
        if not name:
            continue
        val = p.get("field_value_name")
        if val in (None, "", []):
            val = p.get("field_value")
        out[name] = _text(val)
    return out


def _lookup(props: dict, item: dict, fields: tuple, *inline_keys: str) -> str:
    for f in fields:
        if props.get(f):
            return props[f]
    for k in inline_keys:
        if _text(item.get(k)):
            return _text(item.get(k))
    return ""


def _norm_priority(v: str) -> str:
    return _PRIORITY_MAP.get(v.strip().lower(), "med") if v else "med"


def parse_qtest(content: bytes) -> ImportResult:
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        return ImportResult(warnings=[f"JSON parse error: {e}"], format_detected="qtest")

    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        records = data.get("items") or data.get("test-cases") or data.get("testCases") or []
    else:
        records = []

    if not isinstance(records, list) or not records:
        return ImportResult(
            warnings=["No qTest records found (expected a test-case array or 'items')"],
            format_detected="qtest",
        )

    tests: list[TestData] = []
    warnings: list[str] = []

    for item in records:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("name") or item.get("title"))
        if not title:
            warnings.append(f"Skipped qTest case with no name (pid={_text(item.get('pid'))})")
            continue

        props = _properties(item)

        folder = _lookup(props, item, _FOLDER_FIELDS, "module_name", "parent_module").strip("/")
        priority = _norm_priority(_lookup(props, item, _PRIORITY_FIELDS, "priority"))
        owner = _lookup(props, item, _OWNER_FIELDS, "created_by")
        automation = _lookup(props, item, _AUTOMATION_FIELDS).lower()
        automated = automation in ("yes", "true", "automated", "automation")

        raw_tags = _lookup(props, item, _TAG_FIELDS)
        tags = [t.strip() for t in raw_tags.replace(";", ",").split(",") if t.strip()] if raw_tags else []

        tests.append(TestData(
            title=title,
            folder_path=folder,
            type="automated" if automated else "manual",
            status="pending",
            priority=priority,
            owner=owner,
            tags=tags,
            source_id=_text(item.get("pid") or item.get("id")),
        ))

    return ImportResult(
        tests=tests,
        warnings=warnings,
        format_detected="qtest (json)",
        source_provider="qtest",
    )
