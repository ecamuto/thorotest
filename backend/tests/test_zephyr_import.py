"""Unit tests for the Zephyr Scale JSON importer and its detection."""
import json

from backend.importers import parse_zephyr, detect_format


def _b(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ── Detection ──────────────────────────────────────────────────────────────

def test_detect_zephyr_by_extension_and_markers():
    content = _b({"values": [{"key": "PROJ-T1", "name": "x", "objective": "y"}]})
    assert detect_format("export.json", content) == "zephyr"


def test_detect_generic_json_not_zephyr():
    content = _b({"tests": [{"title": "x"}]})
    assert detect_format("export.json", content) == "json"


def test_detect_zephyr_without_extension():
    content = _b({"values": [{"key": "PROJ-T1", "name": "x", "testScript": {}}]})
    assert detect_format("noext", content) == "zephyr"


# ── Test cases ───────────────────────────────────────────────────────────────

def test_parse_scalar_fields():
    content = _b({"values": [{
        "key": "PROJ-T1",
        "name": "Login with valid creds",
        "folder": "/Login/OAuth",
        "priority": "High",
        "status": "Approved",
        "owner": "jsmith",
        "labels": ["smoke", "regression"],
        "objective": "verify login",
    }]})
    result = parse_zephyr(content)
    assert result.format_detected == "zephyr (json)"
    assert len(result.tests) == 1
    t = result.tests[0]
    assert t.title == "Login with valid creds"
    assert t.folder_path == "Login/OAuth"   # leading slash stripped
    assert t.priority == "high"
    assert t.type == "manual"
    assert t.owner == "jsmith"
    assert t.tags == ["smoke", "regression"]
    assert t.source_id == "PROJ-T1"


def test_parse_object_shaped_fields():
    content = _b({"values": [{
        "key": "PROJ-T2",
        "name": "Object shaped",
        "folder": {"fullName": "/A/B"},
        "priority": {"name": "Normal"},
        "status": {"name": "Draft"},
        "owner": {"displayName": "Jane Doe"},
    }]})
    t = parse_zephyr(content).tests[0]
    assert t.folder_path == "A/B"
    assert t.priority == "med"          # Normal → med
    assert t.owner == "Jane Doe"


def test_automated_flag():
    content = _b({"values": [
        {"key": "T1", "name": "auto", "automated": True},
        {"key": "T2", "name": "manual by type", "testType": "Manual"},
    ]})
    tests = parse_zephyr(content).tests
    assert tests[0].type == "automated"
    assert tests[1].type == "manual"


def test_missing_name_is_warned_and_skipped():
    content = _b({"values": [{"key": "PROJ-T9"}]})
    result = parse_zephyr(content)
    assert result.tests == []
    assert any("no name" in w for w in result.warnings)


# ── Executions → runs ────────────────────────────────────────────────────────

def test_executions_grouped_into_runs():
    content = _b({"values": [
        {"key": "PROJ-T1", "name": "Case one"},
        {"key": "PROJ-T2", "name": "Case two"},
        {"testCase": {"key": "PROJ-T1"}, "testCycle": {"name": "Regression"}, "status": "Pass"},
        {"testCase": {"key": "PROJ-T2"}, "testCycle": {"name": "Regression"}, "status": "Fail"},
    ]})
    result = parse_zephyr(content)
    assert len(result.tests) == 2
    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.name == "Regression"
    statuses = {c.test_title: c.status for c in run.cases}
    assert statuses == {"Case one": "pass", "Case two": "fail"}


def test_execution_for_unknown_case_warns():
    content = _b({"values": [
        {"testCaseKey": "PROJ-T99", "testCycle": "Cycle", "status": "Pass"},
    ]})
    result = parse_zephyr(content)
    assert result.runs == []
    assert any("unknown test case" in w for w in result.warnings)


# ── Envelope variants ────────────────────────────────────────────────────────

def test_bare_array_accepted():
    content = _b([{"key": "T1", "name": "bare"}])
    assert len(parse_zephyr(content).tests) == 1


def test_empty_values_warns():
    result = parse_zephyr(_b({"values": []}))
    assert result.tests == []
    assert result.warnings


def test_bad_json_warns():
    result = parse_zephyr(b"{not json")
    assert "JSON parse error" in result.warnings[0]
