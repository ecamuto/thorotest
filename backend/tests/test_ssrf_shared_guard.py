"""S-8 (SECURITY M-1): shared SSRF guard on admin-controlled outbound URLs —
GitLab self-hosted api_base and Jira base_url, checked fail-fast at
integration save (no DNS) and with full resolution in the HTTP clients."""
import socket

import pytest

from backend.net_guard import assert_public_http_url, UnsafeURLError


class TestGuardResolveModes:
    def test_literal_private_ip_blocked_without_dns(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("DNS lookup attempted in resolve=False mode")
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("http://169.254.169.254/latest/meta-data", resolve=False)
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("https://10.0.0.5/api/v4", resolve=False)

    def test_localhost_hostname_blocked_without_dns(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("http://localhost:8929/api/v4", resolve=False)
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("http://evil.localhost/x", resolve=False)

    def test_public_hostname_passes_without_dns(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("DNS lookup attempted in resolve=False mode")
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        assert_public_http_url("https://acme.atlassian.net", resolve=False)  # no raise

    def test_resolve_mode_blocks_internal_resolution(self, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 443))],
        )
        with pytest.raises(UnsafeURLError):
            assert_public_http_url("https://internal-gitlab.corp")

    def test_escape_env_disables(self, monkeypatch):
        monkeypatch.setenv("NET_GUARD_ALLOW_PRIVATE_HOSTS", "1")
        assert_public_http_url("http://127.0.0.1:8929/api/v4")  # no raise


class TestClientConstructorsGuarded:
    def test_gitlab_client_refuses_private_api_base(self, monkeypatch):
        monkeypatch.delenv("NET_GUARD_ALLOW_PRIVATE_HOSTS", raising=False)
        monkeypatch.delenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", raising=False)
        from backend.gitlab_sync import GitLabClient
        with pytest.raises(UnsafeURLError):
            GitLabClient("http://127.0.0.1:8929/api/v4")

    def test_jira_client_refuses_private_base_url(self, monkeypatch):
        monkeypatch.delenv("NET_GUARD_ALLOW_PRIVATE_HOSTS", raising=False)
        monkeypatch.delenv("WEBHOOK_ALLOW_PRIVATE_HOSTS", raising=False)
        from backend.jira_sync import JiraClient
        with pytest.raises(UnsafeURLError):
            JiraClient("https://10.1.2.3", "e@e.com", "tok")


class TestIntegrationSaveValidation:
    def test_create_jira_with_private_ip_rejected(self, client):
        r = client.post("/api/integrations", json={
            "id": "int-evil-jira", "name": "Jira", "type": "jira",
            "config": {"base_url": "https://10.0.0.5", "email": "e@e.com",
                       "api_token": "t", "project_key": "X"},
        })
        assert r.status_code == 422
        assert "Unsafe integration URL" in r.json()["detail"]

    def test_create_gitlab_with_metadata_api_base_rejected(self, client):
        r = client.post("/api/integrations", json={
            "id": "int-evil-gl", "name": "GL", "type": "vcs",
            "config": {"provider": "gitlab",
                       "repo_url": "https://gitlab.com/acme/web",
                       "api_base": "http://169.254.169.254/api/v4"},
        })
        assert r.status_code == 422

    def test_patch_retarget_to_private_rejected(self, client):
        r = client.post("/api/integrations", json={
            "id": "int-gl-ok", "name": "GL", "type": "vcs",
            "config": {"provider": "gitlab",
                       "repo_url": "https://gitlab.com/acme/web", "token": "glpat-x"},
        })
        assert r.status_code == 201
        r = client.patch("/api/integrations/int-gl-ok", json={
            "config": {"provider": "gitlab",
                       "repo_url": "https://gitlab.com/acme/web",
                       "api_base": "http://192.168.0.1/api/v4", "token": ""},
        })
        assert r.status_code == 422

    def test_create_public_jira_passes_offline(self, client, monkeypatch):
        # Save-time validation must not do DNS: prove it by making resolution
        # impossible.
        def boom(*a, **k):
            raise AssertionError("DNS lookup attempted at integration save")
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        r = client.post("/api/integrations", json={
            "id": "int-jira-ok", "name": "Jira", "type": "jira",
            "config": {"base_url": "https://acme.atlassian.net", "email": "e@e.com",
                       "api_token": "t", "project_key": "PAY"},
        })
        assert r.status_code == 201
