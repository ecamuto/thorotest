"""Unit tests for the qTest JSON importer and its detection."""
import json

from backend.importers import parse_qtest, detect_format


def _b(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ── Detection ──────────────────────────────────────────────────────────────

def test_detect_qtest_by_version_id():
    content = _b({"items": [{"pid": "TC-1", "name": "x", "test_case_version_id": 9}]})
    assert detect_format("qtest.json", content) == "qtest"


def test_detect_qtest_by_pid_and_properties():
    content = _b([{"pid": "TC-1", "name": "x",
                   "properties": [{"field_name": "Priority", "field_value_name": "High"}]}])
    assert detect_format("qtest.json", content) == "qtest"


def test_generic_json_not_qtest():
    assert detect_format("g.json", _b({"tests": [{"title": "x"}]})) == "json"


def test_zephyr_and_xray_win_over_qtest():
    assert detect_format("z.json", _b({"values": [{"key": "P-1", "name": "x", "objective": "y"}]})) == "zephyr"
    assert detect_format("x.json", _b([{"testtype": "Manual", "fields": {"summary": "s"}}])) == "xray"


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_parse_properties_array():
    content = _b({"items": [{
        "pid": "TC-5",
        "name": "Login works",
        "properties": [
            {"field_name": "Priority", "field_value_name": "High"},
            {"field_name": "Module", "field_value": "Login/OAuth"},
            {"field_name": "Automation", "field_value_name": "Yes"},
            {"field_name": "Assigned To", "field_value_name": "jsmith"},
            {"field_name": "Tags", "field_value": "smoke;regression"},
        ],
    }]})
    result = parse_qtest(content)
    assert result.format_detected == "qtest (json)"
    assert result.source_provider == "qtest"
    t = result.tests[0]
    assert t.title == "Login works"
    assert t.folder_path == "Login/OAuth"
    assert t.priority == "high"
    assert t.type == "automated"
    assert t.owner == "jsmith"
    assert t.tags == ["smoke", "regression"]
    assert t.source_id == "TC-5"


def test_field_value_name_preferred_over_id():
    content = _b([{
        "pid": "TC-9", "name": "case",
        "properties": [{"field_name": "Priority", "field_value": "1", "field_value_name": "High"}],
    }])
    # field_value_name "High" wins over the raw id "1".
    assert parse_qtest(content).tests[0].priority == "high"


def test_numeric_priority_id_fallback():
    content = _b([{
        "pid": "TC-9", "name": "case",
        "properties": [{"field_name": "Priority", "field_value": "3"}],
    }])
    # No field_value_name → falls back to numeric id 3 → low.
    assert parse_qtest(content).tests[0].priority == "low"


def test_missing_name_warns():
    content = _b({"items": [{"pid": "TC-9", "properties": []}]})
    result = parse_qtest(content)
    assert result.tests == []
    assert any("no name" in w for w in result.warnings)


def test_bare_array_and_empty():
    assert len(parse_qtest(_b([{"pid": "TC-1", "name": "bare"}])).tests) == 1
    assert parse_qtest(_b({"items": []})).warnings


def test_bad_json_warns():
    assert "JSON parse error" in parse_qtest(b"{bad").warnings[0]
