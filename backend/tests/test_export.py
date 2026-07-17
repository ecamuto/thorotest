"""Tests for Phase 8 export endpoints:
  GET /api/runs/{id}/export?format=csv
  GET /api/runs/{id}/export?format=pdf
  GET /api/tests/export?format=csv
"""
import pytest


class TestExportEndpoints:

    # --- Run CSV export ---

    def test_run_export_csv_requires_auth(self, seeded):
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        res = bare.get("/api/runs/R-TEST/export?format=csv")
        assert res.status_code == 401

    def test_run_export_csv_returns_200(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=csv")
        assert res.status_code == 200

    def test_run_export_csv_content_type(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=csv")
        assert "text/csv" in res.headers.get("content-type", "")

    def test_run_export_csv_content_disposition(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=csv")
        cd = res.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd

    def test_run_export_csv_header_row(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=csv")
        # Strip BOM before parsing
        text = res.content.decode("utf-8-sig")
        first_line = text.splitlines()[0]
        assert "test_name" in first_line
        assert "status" in first_line
        assert "assigned_to" in first_line
        assert "duration" in first_line
        assert "actual_result" in first_line

    def test_run_export_csv_404_on_missing_run(self, auth_client):
        tester = auth_client("tester")
        res = tester.get("/api/runs/nonexistent-run-id/export?format=csv")
        assert res.status_code == 404

    def test_run_export_csv_invalid_format(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=xml")
        assert res.status_code == 400

    # --- Run PDF export ---

    def test_run_export_pdf_requires_auth(self, seeded):
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        res = bare.get("/api/runs/R-TEST/export?format=pdf")
        assert res.status_code == 401

    def test_run_export_pdf_returns_200(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=pdf")
        assert res.status_code == 200

    def test_run_export_pdf_content_type(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=pdf")
        assert "application/pdf" in res.headers.get("content-type", "")

    def test_run_export_pdf_content_disposition(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=pdf")
        cd = res.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".pdf" in cd

    def test_run_export_pdf_is_pdf_bytes(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=pdf")
        # PDF files start with %PDF magic bytes
        assert res.content[:4] == b"%PDF"

    # --- Library CSV export ---

    def test_tests_export_csv_requires_auth(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        res = bare.get("/api/tests/export?format=csv")
        assert res.status_code == 401

    def test_tests_export_csv_returns_200(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv")
        assert res.status_code == 200

    def test_tests_export_csv_content_type(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv")
        assert "text/csv" in res.headers.get("content-type", "")

    def test_tests_export_csv_content_disposition(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv")
        cd = res.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd

    def test_tests_export_csv_header_row(self, auth_client, seeded):
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv")
        text = res.content.decode("utf-8-sig")
        first_line = text.splitlines()[0]
        assert "title" in first_line
        assert "folder" in first_line
        assert "priority" in first_line
        assert "status" in first_line
        assert "steps_count" in first_line
        assert "created_at" in first_line

    def test_tests_export_csv_folder_filter(self, auth_client, seeded):
        """folder_id param filters results; empty folder returns 0 data rows (header only)."""
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv&folder_id=nonexistent-folder-xyz")
        assert res.status_code == 200
        text = res.content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        # Only header row — no matching tests
        assert len(lines) == 1

    def test_tests_export_invalid_format(self, auth_client):
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=pdf")
        assert res.status_code == 400

    # --- CSV formula-injection neutralization (SECURITY M-3) ---

    def test_tests_export_neutralizes_formula_titles(self, auth_client, seeded, db):
        from backend import models
        db.add(models.Test(id="TC-EVIL", title='=HYPERLINK("http://evil","x")',
                           folder_id="checkout", type="manual", status="pending"))
        db.flush()
        tester = auth_client("tester")
        res = tester.get("/api/tests/export?format=csv")
        assert res.status_code == 200
        text = res.content.decode("utf-8-sig")
        evil_line = next(l for l in text.splitlines() if "HYPERLINK" in l)
        # csv module quotes the cell (it contains a comma); the payload inside
        # must start with the neutralizing apostrophe, not a raw '='
        assert "'=HYPERLINK" in evil_line
        assert not evil_line.startswith("=")

    def test_run_export_neutralizes_formula_cells(self, auth_client, seeded, db):
        from backend import models
        db.add(models.Test(id="TC-EVIL2", title="+cmd|' /C calc'!A0",
                           folder_id="checkout", type="manual", status="pending"))
        db.add(models.RunCase(run_id="R-TEST", test_id="TC-EVIL2", status="pending",
                              actual_result="@SUM(1+9)*cmd"))
        db.flush()
        tester = auth_client("tester")
        res = tester.get("/api/runs/R-TEST/export?format=csv")
        assert res.status_code == 200
        text = res.content.decode("utf-8-sig")
        evil_line = next(l for l in text.splitlines() if "cmd|" in l)
        assert "'+cmd|" in evil_line
        assert "'@SUM" in evil_line
