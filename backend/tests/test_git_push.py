"""Reverse "Tests as Code" sync — serializer + write-back (github + gitlab)."""
import pytest

from backend import models, github_sync, gitlab_sync, git_push, gitlab_actions
from backend.importers import parse_yaml_test, serialize_yaml_test
from backend.importers.base import ImportResult, TestData as TD, RunData, CaseResult
from backend.importers.junit_xml import extract_case_id, parse_junit_xml
from backend.importers.persist import persist_import_result


# ── serializer round-trip ───────────────────────────────────────

def test_serialize_yaml_test_round_trips():
    fields = {
        "id": "TC-2301", "title": "Stripe charge", "type": "automated",
        "runner": "playwright", "status": "pass", "priority": "high",
        "owner": "anna@example.com", "tags": ["smoke", "payment"],
        "folder": "Checkout/Payment",
    }
    text = serialize_yaml_test(fields)
    parsed = parse_yaml_test(text)
    assert parsed["id"] == "TC-2301"
    assert parsed["title"] == "Stripe charge"
    assert parsed["type"] == "automated"
    assert parsed["priority"] == "high"
    assert parsed["runner"] == "playwright"
    assert parsed["tags"] == ["smoke", "payment"]
    assert parsed["folder_path"] == "Checkout/Payment"
    # status is owned by CI run results, never written back into the file
    assert "status:" not in text


def test_serialize_yaml_test_omits_empty():
    text = serialize_yaml_test({"title": "bare", "type": "manual",
                                "runner": None, "owner": "", "tags": [], "folder": ""})
    assert "runner" not in text
    assert "owner" not in text
    assert "tags" not in text
    assert "folder" not in text
    assert "title: bare" in text


def test_serialize_yaml_test_key_order():
    text = serialize_yaml_test({"id": "TC-1", "title": "T", "type": "manual"})
    assert text.index("id:") < text.index("title:") < text.index("type:")


# ── folder path rebuild ─────────────────────────────────────────

def test_folder_path_rebuilds_hierarchy(db):
    db.add(models.Folder(id="F-A", name="Checkout", parent_id=None))
    db.add(models.Folder(id="F-B", name="Payment", parent_id="F-A"))
    db.commit()
    assert git_push._folder_path(db, "F-B") == "Checkout/Payment"
    assert git_push._folder_path(db, None) == ""


# ── conflict guard ──────────────────────────────────────────────

def test_check_conflict():
    git_push.check_conflict(None, "anything")           # new file: no conflict
    git_push.check_conflict("same\n", "same")            # unchanged: ok (norm)
    with pytest.raises(git_push.PushConflict):
        git_push.check_conflict("changed on git", "what we synced")


# ── fakes ───────────────────────────────────────────────────────

def _make_test(db, **over):
    defaults = dict(
        id="TC-P1", title="pushable", type="automated", status="pass",
        priority="high", runner="playwright", owner="qa@acme.com", tags=["smoke"],
        repo_url="https://github.com/acme/web", source_path="tests/a.yml",
        source_ref="oldsha", source_body='id: TC-P1\ntitle: "old"\n',
        source_synced_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(over)
    t = models.Test(**defaults)
    db.add(t)
    db.commit()
    return t


class _FakeGH:
    instance = None

    def __init__(self, *a, **k):
        _FakeGH.instance = self
        self.written = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def get_file_meta(self, owner, repo, path, ref):
        return ('id: TC-P1\ntitle: "old"\n', "blobsha")  # matches source_body → no conflict

    def put_file(self, owner, repo, path, content, message, branch, sha=None):
        self.written = {"path": path, "content": content, "branch": branch, "sha": sha}
        return "newsha999"


class _FakeGL:
    instance = None

    def __init__(self, *a, **k):
        _FakeGL.instance = self
        self.written = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def get_file_opt(self, project, path, ref):
        return 'id: TC-P1\ntitle: "old"\n'

    def write_file(self, project, path, content, branch, message, update):
        self.written = {"path": path, "content": content, "branch": branch, "update": update}

    def latest_commit(self, project, branch):
        return "glnewsha"


# ── github push_test ────────────────────────────────────────────

def test_github_push_test_commits_and_updates_row(db, monkeypatch):
    monkeypatch.setattr(github_sync, "GitHubClient", _FakeGH)
    t = _make_test(db, title="edited in ThoroTest")
    intg = models.Integration(id="i1", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": t.repo_url, "branch": "main", "token": "ghp"})

    stats = github_sync.push_test(db, intg, t)
    assert stats["committed"] is True
    assert stats["commit"] == "newsha999"
    assert stats["path"] == "tests/a.yml"
    # written YAML reflects the edited title; row advanced to the new commit
    assert "edited in ThoroTest" in _FakeGH.instance.written["content"]
    assert _FakeGH.instance.written["sha"] == "blobsha"
    assert t.source_ref == "newsha999"
    assert "edited in ThoroTest" in t.source_body


def test_github_push_test_conflict(db, monkeypatch):
    class _Diverged(_FakeGH):
        def get_file_meta(self, owner, repo, path, ref):
            return ("someone changed this on git", "blobsha")

    monkeypatch.setattr(github_sync, "GitHubClient", _Diverged)
    t = _make_test(db)
    intg = models.Integration(id="i2", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": t.repo_url, "branch": "main"})
    with pytest.raises(git_push.PushConflict):
        github_sync.push_test(db, intg, t)
    assert t.source_ref == "oldsha"   # unchanged on conflict


# ── gitlab push_test ────────────────────────────────────────────

def test_github_push_test_creates_new_file(db, monkeypatch):
    class _New(_FakeGH):
        def get_file_meta(self, owner, repo, path, ref):
            return None, None   # file doesn't exist yet → create, no conflict

    monkeypatch.setattr(github_sync, "GitHubClient", _New)
    t = _make_test(db, source_body=None)   # never synced content
    intg = models.Integration(id="i-new", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": t.repo_url, "branch": "main"})
    stats = github_sync.push_test(db, intg, t)
    assert stats["committed"] is True
    assert _FakeGH.instance.written["sha"] is None   # create path: no blob sha


# ── gitlab push_test ────────────────────────────────────────────

def test_gitlab_push_test_creates_new_file(db, monkeypatch):
    class _New(_FakeGL):
        def get_file_opt(self, project, path, ref):
            return None   # file absent → POST (create)

    monkeypatch.setattr(gitlab_sync, "GitLabClient", _New)
    t = _make_test(db, id="TC-GLN", repo_url="https://gitlab.com/acme/web", source_body=None)
    intg = models.Integration(id="i-gln", name="GL", type="vcs_ci", icon="gitlab",
                              config={"provider": "gitlab", "repo_url": t.repo_url, "branch": "main"})
    stats = gitlab_sync.push_test(db, intg, t)
    assert stats["commit"] == "glnewsha"
    assert _FakeGL.instance.written["update"] is False   # create, not update


def test_gitlab_push_test_commits_and_updates_row(db, monkeypatch):
    monkeypatch.setattr(gitlab_sync, "GitLabClient", _FakeGL)
    t = _make_test(db, id="TC-GL", repo_url="https://gitlab.com/acme/web",
                   title="gl edit")
    intg = models.Integration(id="i3", name="GL", type="vcs_ci", icon="gitlab",
                              config={"provider": "gitlab", "repo_url": t.repo_url,
                                      "branch": "main", "token": "glpat"})
    stats = gitlab_sync.push_test(db, intg, t)
    assert stats["commit"] == "glnewsha"
    assert _FakeGL.instance.written["update"] is True
    assert "gl edit" in _FakeGL.instance.written["content"]
    assert t.source_ref == "glnewsha"


# ── endpoint ────────────────────────────────────────────────────

def test_push_endpoint_dispatches_to_provider(client, db, monkeypatch):
    monkeypatch.setattr(github_sync, "GitHubClient", _FakeGH)
    _make_test(db, id="TC-EP")
    db.add(models.Integration(id="i-ep", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": "https://github.com/acme/web",
                                      "branch": "main", "token": "ghp"}))
    db.commit()
    r = client.post("/api/tests/TC-EP/push-to-git")
    assert r.status_code == 200, r.text
    assert r.json()["commit"] == "newsha999"


def test_push_endpoint_conflict_returns_409(client, db, monkeypatch):
    class _Diverged(_FakeGH):
        def get_file_meta(self, owner, repo, path, ref):
            return ("changed on git", "blobsha")

    monkeypatch.setattr(github_sync, "GitHubClient", _Diverged)
    _make_test(db, id="TC-EP2")
    db.add(models.Integration(id="i-ep2", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": "https://github.com/acme/web", "branch": "main"}))
    db.commit()
    r = client.post("/api/tests/TC-EP2/push-to-git")
    assert r.status_code == 409, r.text


def test_push_endpoint_rejects_non_git_test(client, db):
    _make_test(db, id="TC-NOSRC", repo_url=None, source_path=None)
    r = client.post("/api/tests/TC-NOSRC/push-to-git")
    assert r.status_code == 400


def test_push_endpoint_no_matching_integration(client, db):
    _make_test(db, id="TC-NOINT", repo_url="https://github.com/nomatch/repo")
    r = client.post("/api/tests/TC-NOINT/push-to-git")
    assert r.status_code == 400


def test_find_vcs_integration_skips_jira(db):
    # A jira integration must never be treated as the test's VCS source, even if
    # its config happens to carry a matching repo_url.
    db.add(models.Integration(id="jira", name="Jira", type="jira", icon="jira",
                              config={"repo_url": "https://github.com/acme/web"}))
    db.commit()
    t = _make_test(db, id="TC-J", repo_url="https://github.com/acme/web")
    assert git_push.find_vcs_integration(db, t) is None
    # add the real vcs integration → now found
    db.add(models.Integration(id="gh", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": "https://github.com/acme/web"}))
    db.commit()
    assert git_push.find_vcs_integration(db, t).id == "gh"


# ── A↔B link: CI run results attach to the YAML scheda ──────────

# Convention: the case id appears bracketed or as a trailing token — not
# mid-word before an English word (that boundary is ambiguous).
@pytest.mark.parametrize("parts,expected", [
    (("login [TC-GL-100]",), "TC-GL-100"),
    (("test_login_TC_GL_100",), "TC-GL-100"),
    (("TC-GL-100",), "TC-GL-100"),
    (("plain name", "pkg.TC-42.Case"), "TC-42"),
    (("no id here", "also none"), ""),
])
def test_extract_case_id(parts, expected):
    assert extract_case_id(*parts) == expected


# Regression: "TC" must be a real id prefix, not any word starting with TC.
# A missing separator or a preceding alnum char must NOT match.
@pytest.mark.parametrize("s", [
    "test_TCP_connection",   # TCP — no separator after TC
    "TContext setup",        # word starting TC
    "BTC-100 wallet",        # TC inside "BTC" — preceded by alnum
    "test_tcp_handshake",    # lowercase, not the TC- convention
    "matcher",               # no TC at all
])
def test_extract_case_id_no_false_positive(s):
    assert extract_case_id(s) == ""


def test_junit_parse_sets_source_id():
    xml = (b'<testsuite name="e2e"><testcase name="login [TC-GL-100]" classname="e2e/login"/>'
           b'</testsuite>')
    result = parse_junit_xml(xml)
    assert result.tests[0].source_id == "TC-GL-100"
    assert result.runs[0].cases[0].source_test_id == "TC-GL-100"


def test_gitlab_test_report_sets_source_id():
    report = {"test_suites": [{"name": "e2e", "test_cases": [
        {"name": "login [TC-GL-100]", "classname": "e2e/login", "status": "failed"},
    ]}]}
    result = gitlab_actions.parse_test_report(report, "pipeline #1")
    assert result.tests[0].source_id == "TC-GL-100"
    assert result.runs[0].cases[0].source_test_id == "TC-GL-100"


def test_sync_tags_scheda_with_ci_identity(db):
    files = [("tests/login.yml", 'id: TC-GL-100\ntitle: "Login"\ntype: automated\n')]
    github_sync.sync_repo(db, "https://gitlab.com/a/b", "main", "", None,
                          fetcher=lambda *a: ("sha1", files), link_provider="gitlab-ci")
    t = db.query(models.Test).filter_by(id="TC-GL-100").first()
    assert t.external_provider == "gitlab-ci"
    assert t.external_key == "TC-GL-100"
    assert t.status == "pending"   # not taken from YAML


def test_ci_run_links_to_scheda_no_duplicate_and_updates_status(db):
    # A: sync the scheda (status pending, tagged for gitlab-ci)
    files = [("tests/login.yml", 'id: TC-GL-100\ntitle: "Login scheda"\ntype: automated\n')]
    github_sync.sync_repo(db, "https://gitlab.com/a/b", "main", "", None,
                          fetcher=lambda *a: ("sha1", files), link_provider="gitlab-ci")

    # B: a pipeline result whose case carries the same TC id
    result = ImportResult(
        tests=[TD(title="login e2e", type="automated", status="fail", source_id="TC-GL-100")],
        runs=[RunData(name="pipeline #1", status="done",
                      cases=[CaseResult(test_title="login e2e", status="fail", source_test_id="TC-GL-100")])],
    )
    stats = persist_import_result(db, result, "gitlab-ci", conflict="skip", sync_status=True)

    # no duplicate test created — the run linked to the existing scheda
    linked = db.query(models.Test).filter_by(external_key="TC-GL-100").all()
    assert len(linked) == 1
    assert stats["tests"] == 0 and stats["skipped"] >= 1
    # the scheda now reflects the real run status
    assert linked[0].id == "TC-GL-100"
    assert linked[0].status == "fail"
    # and a RunCase links the run to it
    rc = db.query(models.RunCase).filter_by(test_id="TC-GL-100").first()
    assert rc is not None and rc.status == "fail"


def test_ci_run_without_id_falls_back_and_creates_own_test(db):
    # No scheda synced, no TC id → B creates its own automated test (today's behavior)
    result = ImportResult(
        tests=[TD(title="orphan test", type="automated", status="pass")],
        runs=[RunData(name="run", status="done",
                      cases=[CaseResult(test_title="orphan test", status="pass")])],
    )
    stats = persist_import_result(db, result, "gitlab-ci", conflict="skip", sync_status=True)
    assert stats["tests"] == 1
    assert db.query(models.Test).filter_by(title="orphan test").count() == 1
