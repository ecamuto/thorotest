"""GitLab CI collection logic (no network — fake client / crafted report)."""
from backend import models
from backend.gitlab_actions import (
    parse_test_report, collect_pipeline_results, ci_config,
)


_REPORT = {
    "total_count": 3,
    "test_suites": [
        {"name": "e2e", "test_cases": [
            {"name": "login works", "classname": "e2e.auth", "status": "success"},
            {"name": "checkout fails", "classname": "e2e.checkout", "status": "failed"},
        ]},
        {"name": "unit", "test_cases": [
            {"name": "skipped one", "classname": "unit.misc", "status": "skipped"},
        ]},
    ],
}


def test_report_maps_statuses_and_folders():
    result = parse_test_report(_REPORT, "GL #7")
    assert result.format_detected == "gitlab_test_report"
    assert len(result.tests) == 3
    statuses = {c.test_title: c.status for c in result.runs[0].cases}
    assert statuses == {"login works": "pass", "checkout fails": "fail", "skipped one": "blocked"}
    folders = {t.title: t.folder_path for t in result.tests}
    assert folders["login works"] == "e2e/auth"


class _FakeClient:
    def get_test_report(self, project, pipeline_id):
        assert pipeline_id == 42
        return _REPORT


def test_collect_pipeline_results_imports(db):
    stats = collect_pipeline_results(db, _FakeClient(), "acme/web", 42, "GL pipeline 42")
    assert stats["tests"] == 3 and stats["runs"] == 1

    run = db.query(models.Run).filter(models.Run.name == "GL pipeline 42").first()
    assert run is not None
    assert run.passed == 1 and run.failed == 1 and run.blocked == 1


def test_ci_config_derives_project_and_api_base():
    intg = models.Integration(
        id="i", name="GL", type="vcs_ci", icon="gitlab",
        config={"provider": "gitlab", "repo_url": "http://localhost:8929/root/app",
                "branch": "dev", "token": "glpat-x"},
    )
    cfg = ci_config(intg)
    assert cfg["api_base"] == "http://localhost:8929/api/v4"
    assert cfg["project"] == "root/app"
    assert cfg["ref"] == "dev"
    assert cfg["token"] == "glpat-x"


def test_ci_run_dispatches_gitlab(client, db, monkeypatch):
    from backend.routers import ci as ci_router
    monkeypatch.setattr(ci_router, "_do_dispatch_gitlab", lambda cfg: {"id": 99, "web_url": "http://x/99"})
    monkeypatch.setattr(ci_router, "_orchestrate_gitlab", lambda *a, **k: None)

    db.add(models.Integration(
        id="int-gl-ci", name="GitLab", type="vcs_ci", icon="gitlab",
        config={"provider": "gitlab", "repo_url": "https://gitlab.com/acme/web",
                "branch": "main", "token": "glpat-x"},
    ))
    db.commit()
    r = client.post("/api/integrations/int-gl-ci/ci/run", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "dispatched"
    assert body["workflow"] == "pipeline"
