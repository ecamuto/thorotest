"""Unit tests for the Xray JSON importer and its detection."""
import json

from backend.importers import parse_xray, detect_format


def _b(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


# ── Detection ──────────────────────────────────────────────────────────────

def test_detect_xray_test_definitions():
    content = _b([{"testtype": "Manual", "fields": {"summary": "x"}}])
    assert detect_format("tests.json", content) == "xray"


def test_detect_xray_results():
    content = _b({"info": {"summary": "run"}, "tests": [{"testKey": "P-1", "status": "PASS"}]})
    assert detect_format("results.json", content) == "xray"


def test_generic_json_not_xray():
    assert detect_format("g.json", _b({"tests": [{"title": "x"}]})) == "json"


def test_zephyr_wins_over_xray_when_both_markers():
    # A Zephyr envelope must still classify as zephyr.
    content = _b({"values": [{"key": "P-1", "name": "x", "objective": "y"}]})
    assert detect_format("z.json", content) == "zephyr"


# ── Test definitions ─────────────────────────────────────────────────────────

def test_parse_definitions():
    content = _b([
        {
            "testtype": "Manual",
            "key": "PROJ-1",
            "xray_test_repository_folder": "/Login/OAuth",
            "fields": {
                "summary": "Login works",
                "priority": {"name": "High"},
                "labels": ["smoke", "regression"],
                "assignee": "jsmith",
            },
        },
        {"testtype": "Automated", "key": "PROJ-2", "fields": {"summary": "API check"}},
    ])
    result = parse_xray(content)
    assert result.format_detected == "xray (json)"
    assert result.source_provider == "xray"
    assert len(result.tests) == 2

    t1 = result.tests[0]
    assert t1.title == "Login works"
    assert t1.folder_path == "Login/OAuth"
    assert t1.priority == "high"
    assert t1.type == "manual"
    assert t1.owner == "jsmith"
    assert t1.tags == ["smoke", "regression"]
    assert t1.source_id == "PROJ-1"

    assert result.tests[1].type == "automated"


def test_definition_without_summary_warns():
    content = _b([{"testtype": "Manual", "key": "PROJ-9", "fields": {}}])
    result = parse_xray(content)
    assert result.tests == []
    assert any("no summary" in w for w in result.warnings)


# ── Execution results ────────────────────────────────────────────────────────

def test_parse_results_into_run():
    content = _b({
        "info": {"summary": "Regression run", "testExecutionKey": "PROJ-42"},
        "tests": [
            {"testKey": "PROJ-1", "status": "PASS"},
            {"testKey": "PROJ-2", "status": "FAIL"},
            {"testKey": "PROJ-3", "status": "ABORTED"},
        ],
    })
    result = parse_xray(content)
    assert result.tests == []
    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.name == "Regression run"
    assert run.source_id == "PROJ-42"
    statuses = {c.source_test_id: c.status for c in run.cases}
    assert statuses == {"PROJ-1": "pass", "PROJ-2": "fail", "PROJ-3": "blocked"}


def test_bad_json_warns():
    result = parse_xray(b"{bad")
    assert "JSON parse error" in result.warnings[0]
