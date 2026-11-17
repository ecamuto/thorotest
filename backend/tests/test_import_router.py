import json

import pytest
from fastapi import HTTPException

from backend.importers.base import ImportResult
from backend.routers import import_ as import_router


@pytest.mark.parametrize(
    ("fmt", "attribute", "expects_mapping"),
    [
        ("csv", "parse_csv", True),
        ("xlsx", "parse_xlsx", True),
        ("testrail_xml", "parse_testrail_xml", False),
        ("testlink_xml", "parse_testlink_xml", False),
        ("junit_xml", "parse_junit_xml", False),
        ("json", "parse_json", False),
        ("zephyr", "parse_zephyr", False),
        ("xray", "parse_xray", False),
        ("qtest", "parse_qtest", False),
    ],
)
def test_run_parser_dispatches_every_supported_format(
    monkeypatch, fmt, attribute, expects_mapping
):
    expected = ImportResult(format_detected=fmt)
    calls = []

    def fake_parser(*args):
        calls.append(args)
        return expected

    monkeypatch.setattr(import_router, attribute, fake_parser)
    mapping = {"title": "Name"}
    assert import_router._run_parser(fmt, b"payload", mapping) is expected
    expected_calls = [(b"payload", mapping)] if expects_mapping else [(b"payload",)]
    assert calls == expected_calls


def test_run_parser_rejects_unknown_format_and_provider_fallbacks():
    with pytest.raises(HTTPException) as exc:
        import_router._run_parser("unknown", b"payload", None)
    assert exc.value.status_code == 400

    explicit = ImportResult(source_provider="allure")
    assert import_router._provider_for("json", explicit) == "allure"
    assert import_router._provider_for("junit_xml", ImportResult()) == "junit"
    assert import_router._provider_for("custom", ImportResult()) == "custom"


def test_import_detect_and_preview_return_metadata_and_samples(client):
    csv_response = client.post(
        "/api/import/detect",
        files={"file": ("cases.csv", b"title,status\nLogin,pass\n", "text/csv")},
    )
    assert csv_response.status_code == 200
    assert csv_response.json()["format"] == "csv"
    assert "csv_meta" in csv_response.json()

    payload = json.dumps({
        "tests": [{"title": f"Case {index}", "folder": "API"} for index in range(7)],
        "runs": [{"name": f"Run {index}", "cases": []} for index in range(4)],
    }).encode()
    preview = client.post(
        "/api/import/preview",
        files={"file": ("cases.json", payload, "application/json")},
        data={"format": "json", "column_mapping": '{"title":"name"}'},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["tests"] == 7
    assert body["runs"] == 4
    assert len(body["sample_tests"]) == 5
    assert len(body["sample_runs"]) == 3


def test_import_routes_reject_invalid_mapping_and_oversized_files(
    client, monkeypatch
):
    invalid = client.post(
        "/api/import/preview",
        files={"file": ("cases.json", b"{}", "application/json")},
        data={"format": "json", "column_mapping": "not-json"},
    )
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "column_mapping must be valid JSON"

    invalid_execute = client.post(
        "/api/import/execute",
        files={"file": ("cases.json", b"{}", "application/json")},
        data={"format": "json", "column_mapping": "not-json"},
    )
    assert invalid_execute.status_code == 400

    monkeypatch.setattr(import_router, "MAX_FILE_SIZE", 3)
    for path in ("detect", "preview", "execute"):
        response = client.post(
            f"/api/import/{path}",
            files={"file": ("large.json", b"1234", "application/json")},
        )
        assert response.status_code == 413
