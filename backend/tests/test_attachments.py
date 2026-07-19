import io
import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app


def make_file(content=b"hello test file", filename="test.txt", content_type="text/plain"):
    return ("file", (filename, io.BytesIO(content), content_type))


def test_upload_attachment(client, tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    # Reload env in router
    import backend.routers.attachments as att_module
    monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))

    r = client.post("/api/attachments", data={
        "entity_type": "test",
        "entity_id": "TC-001",
    }, files=[make_file()])
    assert r.status_code == 201
    data = r.json()
    assert data["filename"] == "test.txt"
    assert data["entity_type"] == "test"
    assert data["entity_id"] == "TC-001"
    assert "id" in data


def test_list_attachments(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att_module
    monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))

    # Upload one
    client.post("/api/attachments", data={
        "entity_type": "run_case",
        "entity_id": "42",
    }, files=[make_file(filename="screen.png", content_type="image/png")])

    r = client.get("/api/attachments", params={"entity_type": "run_case", "entity_id": "42"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert any(d["filename"] == "screen.png" for d in data)


def test_download_attachment(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att_module
    monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))

    content = b"file content here"
    upload_r = client.post("/api/attachments", data={
        "entity_type": "test",
        "entity_id": "TC-DL",
    }, files=[make_file(content=content, filename="log.txt")])
    att_id = upload_r.json()["id"]

    r = client.get(f"/api/attachments/{att_id}")
    assert r.status_code == 200
    assert r.content == content


def test_delete_attachment(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att_module
    monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))

    upload_r = client.post("/api/attachments", data={
        "entity_type": "test",
        "entity_id": "TC-DEL",
    }, files=[make_file()])
    att_id = upload_r.json()["id"]
    storage_path = upload_r.json()["storage_path"]
    abs_path = os.path.join(str(tmp_path), storage_path)

    r = client.delete(f"/api/attachments/{att_id}")
    assert r.status_code == 204
    assert not os.path.exists(abs_path)

    r2 = client.get(f"/api/attachments/{att_id}")
    assert r2.status_code == 404


def test_oversized_upload(client, tmp_path, monkeypatch):
    import backend.routers.attachments as att_module
    monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(att_module, "MAX_UPLOAD_MB", 0)  # 0MB limit = any file oversized

    r = client.post("/api/attachments", data={
        "entity_type": "test",
        "entity_id": "TC-BIG",
    }, files=[make_file(content=b"x" * 1024)])  # 1KB > 0MB limit
    assert r.status_code == 413


class TestAttachmentAuthGuards:
    """6 new tests: 401 + 403 per endpoint (POST, GET list, DELETE)."""

    def test_upload_requires_auth(self, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        r = bare.post("/api/attachments", data={"entity_type": "test", "entity_id": "X"},
                      files=[("file", ("t.txt", b"x", "text/plain"))])
        assert r.status_code == 401

    def test_upload_viewer_forbidden(self, auth_client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        c = auth_client("viewer")
        r = c.post("/api/attachments", data={"entity_type": "test", "entity_id": "X"},
                   files=[("file", ("t.txt", b"x", "text/plain"))])
        assert r.status_code == 403

    def test_list_requires_auth(self, db):
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        r = bare.get("/api/attachments", params={"entity_type": "test", "entity_id": "X"})
        assert r.status_code == 401

    def test_list_viewer_allowed(self, auth_client, db):
        # GET list only requires authentication, not write role
        c = auth_client("viewer")
        r = c.get("/api/attachments", params={"entity_type": "test", "entity_id": "X"})
        assert r.status_code == 200  # viewer can read, returns empty list

    def test_delete_requires_auth(self, db):
        from fastapi.testclient import TestClient
        from backend.main import app
        bare = TestClient(app, raise_server_exceptions=False)
        r = bare.delete("/api/attachments/999")
        assert r.status_code == 401

    def test_delete_viewer_forbidden(self, auth_client, db):
        c = auth_client("viewer")
        r = c.delete("/api/attachments/999")
        assert r.status_code == 403


class TestUploadTypeAllowlist:
    """SECURITY M-2 (roadmap S-5): extension allow-list + safe download headers."""

    def _upload(self, client, filename, content_type="application/octet-stream"):
        return client.post("/api/attachments", data={
            "entity_type": "test", "entity_id": "TC-SEC",
        }, files=[make_file(filename=filename, content_type=content_type)])

    def test_rejects_executable(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        r = self._upload(client, "payload.exe")
        assert r.status_code == 422

    def test_rejects_html(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        r = self._upload(client, "xss.html", "text/html")
        assert r.status_code == 422

    def test_rejects_svg(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        r = self._upload(client, "vector.svg", "image/svg+xml")
        assert r.status_code == 422

    def test_rejects_no_extension(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        r = self._upload(client, "noext")
        assert r.status_code == 422

    def test_extension_check_is_case_insensitive(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        r = self._upload(client, "SHOT.PNG", "image/png")
        assert r.status_code == 201

    def test_download_forces_attachment_and_nosniff(self, client, tmp_path, monkeypatch):
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        up = self._upload(client, "report.txt", "text/plain")
        att_id = up.json()["id"]
        r = client.get(f"/api/attachments/{att_id}")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert r.headers.get("x-content-type-options") == "nosniff"

    def test_download_neuters_spoofed_html_mime(self, client, tmp_path, monkeypatch):
        # A .txt upload whose declared content_type claims text/html must not
        # be served back as text/html.
        import backend.routers.attachments as att_module
        monkeypatch.setattr(att_module, "UPLOAD_DIR", str(tmp_path))
        up = self._upload(client, "sneaky.txt", "text/html")
        att_id = up.json()["id"]
        r = client.get(f"/api/attachments/{att_id}")
        assert r.headers["content-type"].startswith("application/octet-stream")


class TestSecurityHeaders:
    def test_csp_and_nosniff_on_responses(self, client):
        r = client.get("/api/config")
        csp = r.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "object-src 'none'" in csp
        assert r.headers.get("x-content-type-options") == "nosniff"
