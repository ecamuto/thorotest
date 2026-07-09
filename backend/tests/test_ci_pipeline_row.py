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
