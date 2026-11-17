import json

from backend.importers.json_importer import parse_json


def test_generic_json_maps_tests_runs_defects_and_skips_untitled_rows():
    payload = {
        "tests": [
            {
                "id": 17,
                "title": "Checkout works",
                "folder": "Commerce/Checkout",
                "type": "automated",
                "status": "pass",
                "priority": "blocker",
                "owner": "QA",
                "tags": ["smoke"],
            },
            {"name": "Fallback title", "section": "Fallback"},
            {"id": 99},
        ],
        "runs": [
            {
                "title": "Nightly",
                "status": "done",
                "results": [
                    {"name": "Checkout works", "status": "passed"},
                    {"title": "Fallback title", "status": "skipped"},
                ],
            },
            {"cases": []},
        ],
        "defects": [
            {
                "id": "BUG-7",
                "name": "Payment timeout",
                "status": "open",
                "severity": "major",
                "description": "Provider timed out",
                "test_title": "Checkout works",
            },
            {"id": "BUG-NO-TITLE"},
        ],
    }

    result = parse_json(json.dumps(payload).encode())

    assert result.format_detected == "json (generic)"
    assert result.source_provider == "generic"
    assert [test.title for test in result.tests] == [
        "Checkout works",
        "Fallback title",
    ]
    assert result.tests[0].priority == "critical"
    assert result.tests[0].source_id == "17"
    assert result.tests[1].folder_path == "Fallback"
    assert len(result.runs) == 1
    assert [case.status for case in result.runs[0].cases] == ["pass", "blocked"]
    assert len(result.defects) == 1
    assert result.defects[0].severity == "high"
    assert result.defects[0].source_id == "BUG-7"


def test_allure_json_uses_suite_labels_and_normalizes_results():
    payload = [
        {
            "name": "Successful login",
            "status": "passed",
            "labels": [{"name": "suite", "value": "Authentication"}],
        },
        {
            "fullName": "Fallback name",
            "status": "broken",
            "labels": [{"name": "parentSuite", "value": "Parent"}],
        },
        {"status": "failed"},
    ]

    result = parse_json(json.dumps(payload).encode())

    assert result.format_detected == "json (allure)"
    assert result.source_provider == "allure"
    assert [test.folder_path for test in result.tests] == ["Authentication", "Parent"]
    assert [case.status for case in result.runs[0].cases] == ["pass", "fail"]
    assert result.runs[0].status == "done"


def test_json_parser_reports_invalid_and_unrecognized_documents():
    invalid = parse_json(b"{not-json")
    assert invalid.format_detected == "json"
    assert invalid.warnings and "JSON parse error" in invalid.warnings[0]

    for content in (b"[]", b"[1, 2]", b'"text"'):
        result = parse_json(content)
        assert result.tests == []
        assert result.warnings == [
            "Unrecognised JSON structure — expected object with 'tests' key or Allure array"
        ]


def test_json_defaults_unknown_priority_and_status_values():
    result = parse_json(json.dumps({
        "tests": [{"title": "Unknown priority", "priority": "urgent"}],
        "runs": [{
            "name": "Unknown state",
            "cases": [{"title": "Unknown priority", "status": "mystery"}],
        }],
    }).encode())

    assert result.tests[0].priority == "med"
    assert result.runs[0].cases[0].status == "pending"
