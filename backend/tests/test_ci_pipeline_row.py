"""CI "Run" → Pipeline row on the pipelines page (running → pass/fail)."""
import pytest

from backend import models
from backend.routers.ci import _fmt_duration, _gh_run_seconds, _upsert_pipeline


@pytest.mark.parametrize("secs,out", [
    (252, "4m 12s"), (38, "38s"), (60, "1m 00s"), (0, None), (None, None),
])
def test_fmt_duration(secs, out):
    assert _fmt_duration(secs) == out


def test_gh_run_seconds():
    d = {"run_started_at": "2026-07-09T10:00:00Z", "updated_at": "2026-07-09T10:04:12Z"}
    assert _gh_run_seconds(d) == 252.0
    assert _gh_run_seconds({"created_at": "2026-07-09T10:00:00Z",
                            "updated_at": "2026-07-09T10:00:05Z"}) == 5.0
    assert _gh_run_seconds({}) is None
    assert _gh_run_seconds({"created_at": "x", "updated_at": "y"}) is None


def test_upsert_pipeline_creates_then_updates(db):
    pid = "gl-pipeline-42"
    # dispatch: running row appears
    _upsert_pipeline(db, pid, name="GitLab pipeline #42", platform="gitlab",
                     status="running", commit="abc1234", branch="main", when="just now",
                     url="http://gl/42")
    p = db.query(models.Pipeline).filter_by(id=pid).first()
    assert p is not None and p.status == "running" and p.platform == "gitlab"
    assert p.commit == "abc1234" and p.duration is None
    assert p.url == "http://gl/42"

    # completion: same id updated in place, no duplicate
    _upsert_pipeline(db, pid, status="fail", duration=_fmt_duration(252))
    assert db.query(models.Pipeline).filter_by(id=pid).count() == 1
    p = db.query(models.Pipeline).filter_by(id=pid).first()
    assert p.status == "fail"
    assert p.duration == "4m 12s"
    # None fields don't clobber existing values
    assert p.name == "GitLab pipeline #42"
    assert p.commit == "abc1234"


# ── ci_run endpoint: dispatch + error paths ─────────────────────

def _gl_integration(db, iid="int-gl"):
    db.add(models.Integration(
        id=iid, name="GitLab", type="vcs_ci", icon="gitlab",
        config={"provider": "gitlab", "repo_url": "https://gitlab.com/acme/web",
                "branch": "main", "token": "glpat-x"}))
    db.commit()


def test_ci_run_creates_running_pipeline_row(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    monkeypatch.setattr(ci_router, "_do_dispatch_gitlab",
                        lambda cfg: {"id": 99, "web_url": "http://x/99", "sha": "deadbeef123", "ref": "main"})
    monkeypatch.setattr(ci_router, "_orchestrate_gitlab", lambda *a, **k: None)
    _gl_integration(db)

    r = client.post("/api/integrations/int-gl/ci/run", json={"run_name": "My run"})
    assert r.status_code == 200, r.text
    # a running row now shows on the pipelines page
    p = db.query(models.Pipeline).filter_by(id="gl-pipeline-99").first()
    assert p is not None
    assert p.status == "running" and p.platform == "gitlab"
    assert p.commit == "deadbee" and p.branch == "main"
    assert p.name == "My run"
    assert p.url == "http://x/99"   # links to the run on GitLab


def test_ci_run_unknown_integration_404(client, db):
    r = client.post("/api/integrations/nope/ci/run", json={})
    assert r.status_code == 404


def test_ci_run_non_vcs_integration_400(client, db):
    db.add(models.Integration(id="mystery", name="Mystery", type="vcs_ci", icon="plug",
                              config={"repo_url": "https://example.com/a/b"}))
    db.commit()
    r = client.post("/api/integrations/mystery/ci/run", json={})
    assert r.status_code == 400


def test_delete_pipeline(client, db):
    db.add(models.Pipeline(id="wf-del", name="ci.yml", platform="github", status="pass"))
    db.commit()
    r = client.delete("/api/pipelines/wf-del")
    assert r.status_code == 204
    assert db.query(models.Pipeline).filter_by(id="wf-del").first() is None


def test_delete_pipeline_unknown_404(client, db):
    assert client.delete("/api/pipelines/nope").status_code == 404


# ── pipeline row expand → run test cases ────────────────────────

def test_pipeline_cases_returns_run_cases(client, db):
    db.add(models.Test(id="TC-EXP1", title="Expand me"))
    db.add(models.Run(id="R-EXP", name="CI run", status="fail", total=2))
    db.add(models.Pipeline(id="wf-exp", name="ci.yml", platform="github",
                           status="fail", run_id="R-EXP"))
    db.add(models.RunCase(run_id="R-EXP", test_id="TC-EXP1", status="pass"))
    db.add(models.RunCase(run_id="R-EXP", test_id="TC-EXP1", status="fail"))
    db.commit()

    r = client.get("/api/pipelines/wf-exp/cases")
    assert r.status_code == 200, r.text
    cases = r.json()
    assert len(cases) == 2
    assert {c["status"] for c in cases} == {"pass", "fail"}
    assert cases[0]["title"] == "Expand me"       # joined test title
    assert cases[0]["test_id"] == "TC-EXP1"


def test_pipeline_cases_empty_when_no_run_linked(client, db):
    db.add(models.Pipeline(id="wf-norun", name="ci.yml", platform="github", status="pass"))
    db.commit()
    r = client.get("/api/pipelines/wf-norun/cases")
    assert r.status_code == 200
    assert r.json() == []


def test_pipeline_cases_unknown_404(client, db):
    assert client.get("/api/pipelines/nope/cases").status_code == 404


# ── reconcile: heal stuck 'running' rows against the provider ────

class _FakeGH:
    """Context-manager stub for GitHubActionsClient."""
    def __init__(self, detail):
        self._detail = detail
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_run(self, owner, repo, run_id): return self._detail


def _gh_running_pipeline(db):
    db.add(models.Integration(id="int-gh", name="GH", type="vcs_ci", icon="github",
                              config={"repo_url": "https://github.com/acme/web", "token": "ghp_x"}))
    db.add(models.Pipeline(id="gh-run-777", name="CI", platform="github",
                           status="running", integration_id="int-gh"))
    db.commit()


def test_reconcile_finalizes_completed_run(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    _gh_running_pipeline(db)
    detail = {"status": "completed", "conclusion": "success",
              "run_started_at": "2026-07-09T10:00:00Z", "updated_at": "2026-07-09T10:02:00Z"}
    monkeypatch.setattr(ci_router, "ci_config",
                        lambda intg: {"owner": "acme", "repo": "web", "token": "ghp_x", "artifact": "junit"})
    monkeypatch.setattr(ci_router, "GitHubActionsClient", lambda token: _FakeGH(detail))

    def _fake_collect(db_, client_, owner, repo, run_id, artifact, run_name):
        db_.add(models.Run(id="R-NEW", name=run_name, status="pass", total=1))
        db_.flush()
        return {"run_ids": ["R-NEW"]}
    monkeypatch.setattr(ci_router, "collect_run_results", _fake_collect)

    n = ci_router.reconcile_running_pipelines(db)
    assert n == 1
    p = db.query(models.Pipeline).filter_by(id="gh-run-777").first()
    assert p.status == "pass"
    assert p.duration == "2m 00s"
    assert p.run_id == "R-NEW"


def test_reconcile_leaves_still_running(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    _gh_running_pipeline(db)
    monkeypatch.setattr(ci_router, "ci_config",
                        lambda intg: {"owner": "acme", "repo": "web", "token": "ghp_x", "artifact": "junit"})
    monkeypatch.setattr(ci_router, "GitHubActionsClient",
                        lambda token: _FakeGH({"status": "in_progress"}))
    assert ci_router.reconcile_running_pipelines(db) == 0
    assert db.query(models.Pipeline).filter_by(id="gh-run-777").first().status == "running"


def test_reconcile_skips_pipeline_without_integration(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    db.add(models.Pipeline(id="gh-run-9", name="CI", platform="github", status="running"))
    db.commit()

    def _boom(*a, **k):
        raise AssertionError("should not query provider without an integration")
    monkeypatch.setattr(ci_router, "GitHubActionsClient", _boom)
    assert ci_router.reconcile_running_pipelines(db) == 0


def test_reconcile_endpoint_returns_fresh_list(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    db.add(models.Pipeline(id="wf-static", name="ci.yml", platform="github", status="pass"))
    db.commit()
    r = client.post("/api/pipelines/reconcile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "updated" in body
    assert any(p["id"] == "wf-static" for p in body["pipelines"])


def test_ci_run_dispatch_failure_502(client, db, monkeypatch):
    from backend.routers import ci as ci_router

    def _boom(cfg):
        raise RuntimeError("gitlab down")
    monkeypatch.setattr(ci_router, "_do_dispatch_gitlab", _boom)
    _gl_integration(db, "int-gl-boom")
    r = client.post("/api/integrations/int-gl-boom/ci/run", json={})
    assert r.status_code == 502
    # no pipeline row left behind on dispatch failure
    assert db.query(models.Pipeline).filter(models.Pipeline.id.like("gl-pipeline-%")).count() == 0
