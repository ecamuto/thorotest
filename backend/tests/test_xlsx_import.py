"""Unit tests for the .xlsx importer and its detection."""
import io

from openpyxl import Workbook

from backend.importers import parse_xlsx, detect_format
from backend.importers.csv_importer import get_xlsx_columns


def _xlsx(headers, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Detection ──────────────────────────────────────────────────────────────

def test_detect_xlsx_by_extension():
    content = _xlsx(["title", "section"], [["A", "F1"]])
    assert detect_format("cases.xlsx", content) == "xlsx"


def test_detect_xlsx_by_zip_magic_without_extension():
    content = _xlsx(["title"], [["A"]])
    assert detect_format("noext", content) == "xlsx"


def test_csv_still_detected():
    assert detect_format("t.csv", b"title,section\na,b") == "csv"


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_parse_xlsx_reuses_csv_column_logic():
    content = _xlsx(
        ["Title", "Section", "Priority", "Type", "Tags", "ID"],
        [
            ["Login valid", "Auth/OAuth", "High", "manual", "smoke;auth", "TC-1"],
            ["Checkout", "Shop", "critical", "automated", "", "TC-2"],
            [None, "skip me", "low", "manual", "", ""],  # no title → skipped
        ],
    )
    result = parse_xlsx(content)
    assert result.format_detected.startswith("xlsx")
    assert len(result.tests) == 2

    t = result.tests[0]
    assert t.title == "Login valid"
    assert t.folder_path == "Auth/OAuth"
    assert t.priority == "high"
    assert t.type == "manual"
    assert t.tags == ["smoke", "auth"]
    assert t.source_id == "TC-1"

    assert result.tests[1].type == "automated"
    assert result.tests[1].priority == "critical"


def test_numeric_cell_coerced_to_string():
    # A numeric ID cell must not break parsing.
    content = _xlsx(["title", "id"], [["Case", 12345]])
    t = parse_xlsx(content).tests[0]
    assert t.source_id == "12345"


def test_no_title_column_warns():
    content = _xlsx(["foo", "bar"], [["a", "b"]])
    result = parse_xlsx(content)
    assert result.tests == []
    assert any("title column" in w for w in result.warnings)


def test_get_xlsx_columns():
    content = _xlsx(["Title", "Section"], [["a", "b"]])
    meta = get_xlsx_columns(content)
    assert meta["headers"] == ["Title", "Section"]
    assert meta["mapping"].get("title") == "Title"


def test_corrupt_xlsx_warns():
    result = parse_xlsx(b"not a real xlsx")
    assert result.tests == []
    assert any("Could not read" in w for w in result.warnings)
