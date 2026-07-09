import pytest

from backend import models, gitlab_sync
from backend.vcs import detect_provider


# ── repo url parsing ────────────────────────────────────────────

@pytest.mark.parametrize("url,api_base,project", [
    ("https://gitlab.com/acme/web", "https://gitlab.com/api/v4", "acme/web"),
    ("https://gitlab.com/acme/web.git", "https://gitlab.com/api/v4", "acme/web"),
    ("https://gitlab.com/acme/web/", "https://gitlab.com/api/v4", "acme/web"),
    ("https://gitlab.com/grp/sub/web", "https://gitlab.com/api/v4", "grp/sub/web"),
    ("http://localhost:8929/root/thorotest", "http://localhost:8929/api/v4", "root/thorotest"),
    ("git@gitlab.com:acme/web.git", "https://gitlab.com/api/v4", "acme/web"),
])
def test_parse_gitlab_repo(url, api_base, project):
    assert gitlab_sync.parse_gitlab_repo(url) == (api_base, project)


def test_parse_gitlab_repo_api_base_override():
    api, proj = gitlab_sync.parse_gitlab_repo(
        "http://gitlab.internal/root/app", api_base="http://api.internal/api/v4")
    assert api == "http://api.internal/api/v4"
    assert proj == "root/app"


def test_parse_gitlab_repo_rejects_bad_url():
    with pytest.raises(ValueError):
        gitlab_sync.parse_gitlab_repo("https://gitlab.com/no-project")


# ── provider detection ──────────────────────────────────────────

def test_detect_provider_explicit():
    assert detect_provider({"provider": "gitlab", "repo_url": "http://x/y/z"}) == "gitlab"


def test_detect_provider_infers_host():
    assert detect_provider({"repo_url": "https://gitlab.com/a/b"}) == "gitlab"
    assert detect_provider({"repo_url": "https://github.com/a/b"}) == "github"


def test_detect_provider_self_hosted_needs_explicit():
    with pytest.raises(ValueError):
        detect_provider({"repo_url": "http://localhost:8929/root/app"})


# ── sync_integration (fake GitLabClient, no network) ────────────

class _FakeGL:
    """Stand-in for GitLabClient: serves a fixed tree + file contents."""
    tree = ["e2e/login.yml", "e2e/checkout.yaml", "README.md"]
    files = {
        "e2e/login.yml": 'id: TC-GL1\ntitle: "GL login"\ntype: automated\nrunner: playwright\nfolder: E2E/Auth\n',
        "e2e/checkout.yaml": 'title: "GL checkout"\ntype: manual\n',
    }

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def latest_commit(self, project, branch):
        return "sha-gl-123"

    def list_yaml_files(self, project, ref, path_prefix):
        return [p for p in self.tree if p.lower().endswith((".yml", ".yaml"))]

    def get_file(self, project, path, ref):
        return self.files[path]


def test_gitlab_sync_integration_creates_tests(db, monkeypatch):
    monkeypatch.setattr(gitlab_sync, "GitLabClient", _FakeGL)
    intg = models.Integration(
        id="int-gitlab", name="GitLab", type="vcs_ci", icon="gitlab",
        config={"provider": "gitlab", "repo_url": "https://gitlab.com/acme/web",
                "branch": "main", "path": "e2e/", "token": "glpat-x"},
    )
    db.add(intg)
    db.commit()

    stats = gitlab_sync.sync_integration(db, intg)
    assert stats["created"] == 2
    assert stats["commit"] == "sha-gl-123"

    t = db.query(models.Test).filter_by(id="TC-GL1").first()
    assert t is not None
    assert t.repo_url == "https://gitlab.com/acme/web"
    assert t.source_path == "e2e/login.yml"
    assert t.source_ref == "sha-gl-123"
    assert t.folder_rel is not None and t.folder_rel.name == "Auth"


def test_gitlab_sync_endpoint(client, db, monkeypatch):
    monkeypatch.setattr(gitlab_sync, "GitLabClient", _FakeGL)
    db.add(models.Integration(
        id="int-gl-ep", name="GitLab", type="vcs_ci", icon="gitlab",
        config={"provider": "gitlab", "repo_url": "https://gitlab.com/acme/web",
                "branch": "main", "path": "e2e/", "token": "glpat-x"},
    ))
    db.commit()
    r = client.post("/api/integrations/int-gl-ep/sync")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2
    assert db.query(models.Test).filter_by(id="TC-GL1").first() is not None
