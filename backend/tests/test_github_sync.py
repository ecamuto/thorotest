import pytest

from backend import models, github_sync
from backend.importers import parse_yaml_test


# ── YAML parsing ────────────────────────────────────────────────

def test_parse_yaml_test_normalizes_fields():
    data = parse_yaml_test(b"""
id: TC-2301
title: "Stripe card charge succeeds on test card"
type: e2e
runner: playwright
status: passed
priority: P1
owner: anna@example.com
tags: [smoke, payment]
folder: Checkout/Payment
""")
    assert data["id"] == "TC-2301"
    assert data["title"] == "Stripe card charge succeeds on test card"
    assert data["type"] == "automated"      # e2e → automated
    assert data["auto"] is True
    assert data["status"] == "pass"          # passed → pass
    assert data["priority"] == "high"        # P1 → high
    assert data["runner"] == "playwright"
    assert data["tags"] == ["smoke", "payment"]
    assert data["folder_path"] == "Checkout/Payment"


def test_parse_yaml_test_defaults_for_manual():
    data = parse_yaml_test("title: Just a title")
    assert data["id"] is None
    assert data["type"] == "manual"
    assert data["auto"] is False
    assert data["priority"] == "med"
    assert data["status"] == "pending"


def test_parse_yaml_test_missing_title_raises():
    with pytest.raises(ValueError):
        parse_yaml_test("id: TC-1\ntype: manual")


def test_parse_yaml_test_invalid_yaml_raises():
    with pytest.raises(ValueError):
        parse_yaml_test("title: 'unterminated")


def test_parse_yaml_test_non_mapping_raises():
    with pytest.raises(ValueError):
        parse_yaml_test("- just\n- a\n- list")


# ── repo url parsing ────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/acme/web", ("acme", "web")),
    ("https://github.com/acme/web.git", ("acme", "web")),
    ("https://github.com/acme/web/", ("acme", "web")),
    ("git@github.com:acme/web.git", ("acme", "web")),
])
def test_parse_repo_url(url, expected):
    assert github_sync.parse_repo_url(url) == expected


def test_parse_repo_url_rejects_non_github():
    with pytest.raises(ValueError):
        github_sync.parse_repo_url("https://gitlab.com/acme/web")


# ── sync_repo upsert (injected fetcher, no network) ─────────────

def _fake_fetcher(files, sha="a3c9f1d"):
    def _f(repo_url, branch, path, token):
        return sha, files
    return _f


def test_sync_repo_creates_tests_with_source(db):
    files = [(
        "tests/checkout/stripe-charge.yml",
        'id: TC-2301\ntitle: "Stripe charge"\ntype: automated\nrunner: playwright\nfolder: Checkout/Payment\n',
    )]
    stats = github_sync.sync_repo(
        db, "https://github.com/acme/web", "main", "tests/", token=None,
        fetcher=_fake_fetcher(files),
    )
    assert stats["created"] == 1
    assert stats["updated"] == 0
    assert stats["commit"] == "a3c9f1d"

    t = db.query(models.Test).filter_by(id="TC-2301").first()
    assert t is not None
    assert t.repo_url == "https://github.com/acme/web"
    assert t.source_path == "tests/checkout/stripe-charge.yml"
    assert t.source_ref == "a3c9f1d"
    assert "Stripe charge" in t.source_body
    assert t.source_synced_at is not None
    # folder hierarchy created
    assert t.folder_rel is not None and t.folder_rel.name == "Payment"


def test_sync_repo_is_idempotent_update_not_duplicate(db):
    files_v1 = [("tests/a.yml", 'id: TC-1\ntitle: "v1"\ntype: manual\n')]
    github_sync.sync_repo(db, "https://github.com/a/b", "main", "", None,
                          fetcher=_fake_fetcher(files_v1, sha="aaa"))

    files_v2 = [("tests/a.yml", 'id: TC-1\ntitle: "v2 renamed"\ntype: automated\n')]
    stats = github_sync.sync_repo(db, "https://github.com/a/b", "main", "", None,
                                  fetcher=_fake_fetcher(files_v2, sha="bbb"))

    assert stats["created"] == 0
    assert stats["updated"] == 1
    rows = db.query(models.Test).filter_by(id="TC-1").all()
    assert len(rows) == 1
    assert rows[0].title == "v2 renamed"
    assert rows[0].auto is True
    assert rows[0].source_ref == "bbb"


def test_sync_repo_matches_by_path_when_no_id(db):
    files = [("tests/x.yml", 'title: "no id test"\ntype: manual\n')]
    github_sync.sync_repo(db, "https://github.com/a/b", "main", "", None,
                          fetcher=_fake_fetcher(files, sha="111"))
    stats = github_sync.sync_repo(db, "https://github.com/a/b", "main", "", None,
                                  fetcher=_fake_fetcher(files, sha="222"))
    assert stats["updated"] == 1
    assert db.query(models.Test).filter_by(source_path="tests/x.yml").count() == 1


def test_sync_repo_skips_bad_yaml_with_warning(db):
    files = [
        ("tests/good.yml", 'title: "ok"\ntype: manual\n'),
        ("tests/bad.yml", "title: 'unterminated"),
    ]
    stats = github_sync.sync_repo(db, "https://github.com/a/b", "main", "", None,
                                  fetcher=_fake_fetcher(files))
    assert stats["created"] == 1
    assert stats["skipped"] == 1
    assert any("bad.yml" in w for w in stats["warnings"])


# ── endpoint + token redaction ──────────────────────────────────

def test_sync_endpoint(client, db, monkeypatch):
    files = [("tests/a.yml", 'id: TC-9\ntitle: "from sync"\ntype: automated\n')]
    monkeypatch.setattr(github_sync, "_fetch_files", _fake_fetcher(files, sha="deadbee"))

    db.add(models.Integration(
        id="int-github-1", name="GitHub", type="vcs_ci", icon="github",
        config={"repo_url": "https://github.com/acme/web", "branch": "main",
                "path": "tests/", "token": "ghp_secret"},
    ))
    db.commit()

    r = client.post("/api/integrations/int-github-1/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    assert body["commit"] == "deadbee"
    assert db.query(models.Test).filter_by(id="TC-9").first() is not None


def test_sync_endpoint_rejects_unknown_provider(client, db):
    # A host that is neither github nor gitlab, with no explicit provider, can't
    # be routed → 400. (gitlab.com is now a supported provider, see test_gitlab_sync.)
    db.add(models.Integration(
        id="int-unknown", name="Mystery", type="vcs_ci", icon="plug",
        config={"repo_url": "https://example.com/acme/web"},
    ))
    db.commit()
    r = client.post("/api/integrations/int-unknown/sync")
    assert r.status_code == 400


def test_integration_out_redacts_token(client, db):
    db.add(models.Integration(
        id="int-github-2", name="GitHub", type="vcs_ci", icon="github",
        config={"repo_url": "https://github.com/a/b", "token": "ghp_secret"},
    ))
    db.commit()
    r = client.get("/api/integrations")
    assert r.status_code == 200
    intg = next(i for i in r.json() if i["id"] == "int-github-2")
    assert intg["config"]["token"] == ""
    assert intg["config"]["token_set"] is True


def test_update_does_not_wipe_token_on_blank(client, db):
    db.add(models.Integration(
        id="int-github-3", name="GitHub", type="vcs_ci", icon="github",
        config={"repo_url": "https://github.com/a/b", "token": "ghp_keep"},
    ))
    db.commit()
    # PATCH with blank token (as the redacted UI would send)
    r = client.patch("/api/integrations/int-github-3", json={
        "config": {"repo_url": "https://github.com/a/b", "branch": "dev", "path": "", "token": ""},
    })
    assert r.status_code == 200
    intg = db.query(models.Integration).filter_by(id="int-github-3").first()
    db.refresh(intg)
    assert intg.config["token"] == "ghp_keep"
    assert intg.config["branch"] == "dev"
