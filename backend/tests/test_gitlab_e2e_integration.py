"""Live end-to-end integration test against a real GitLab CE instance.

This exercises the network-boundary code the unit tests deliberately stub out
(the GitLab REST wrappers, the pipeline trigger/poll/collect path, and the
reverse push) against a running GitLab, in-process — no uvicorn needed.

It SKIPS unless a live GitLab is reachable AND a token is provided, so a normal
`pytest` run is unaffected. To run it:

    cd demo/gitlab && docker compose up -d && ./setup.sh   # prints a glpat-… token
    export GITLAB_E2E_TOKEN=glpat-…
    ./venv/bin/python -m pytest backend/tests/test_gitlab_e2e_integration.py -v

Optional overrides: GITLAB_E2E_URL (default http://localhost:8929),
GITLAB_E2E_REPO (default <url>/root/thorotest-demo). The repo must be the demo
fixtures (schede TC-GL-100/101 + a .gitlab-ci.yml). The pipeline job pulls a
docker image on first run, so the first execution can take a few minutes.
"""
import os
import time
import urllib.error
import urllib.request

import pytest

from backend import models, gitlab_sync, git_push
from backend.gitlab_actions import (
    GitLabActionsClient, ci_config, collect_pipeline_results, _TERMINAL,
)
from backend.gitlab_sync import GitLabClient, parse_gitlab_repo

GL_WEB = os.environ.get("GITLAB_E2E_URL", "http://localhost:8929")
TOKEN = os.environ.get("GITLAB_E2E_TOKEN")
REPO = os.environ.get("GITLAB_E2E_REPO", f"{GL_WEB}/root/thorotest-demo")
LOGIN_YML = "tests/auth/login.yml"
PIPELINE_TIMEOUT = 600


def _gitlab_up() -> bool:
    try:
        urllib.request.urlopen(f"{GL_WEB}/api/v4/version", timeout=3)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401)   # 401 = up but unauthenticated
    except Exception:
        return False
    return True


if not (TOKEN and _gitlab_up()):
    pytest.skip(
        "live GitLab + GITLAB_E2E_TOKEN required (see module docstring)",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration


def _cfg() -> dict:
    return {"provider": "gitlab", "repo_url": REPO, "api_base": f"{GL_WEB}/api/v4",
            "branch": "main", "path": "tests/", "token": TOKEN}


def _integration(db, iid: str):
    intg = models.Integration(id=iid, name="GitLab E2E", type="vcs_ci", icon="gitlab",
                              config=_cfg())
    db.add(intg)
    db.commit()
    return intg


def test_sync_then_ci_links_and_updates_status(db):
    intg = _integration(db, "gl-e2e-1")

    # A: sync the YAML schede — definitions only, status pending, tagged for CI
    stats = gitlab_sync.sync_integration(db, intg)
    assert stats["created"] >= 2
    for tc in ("TC-GL-100", "TC-GL-101"):
        t = db.query(models.Test).filter_by(id=tc).first()
        assert t is not None, f"{tc} not synced"
        assert t.status == "pending"
        assert t.external_provider == "gitlab-ci" and t.external_key == tc

    # B: run the real pipeline and import its result
    cfg = ci_config(intg)
    with GitLabActionsClient(cfg["api_base"], cfg["token"]) as cl:
        pipe = cl.trigger_pipeline(cfg["project"], cfg["ref"])
        pid = pipe["id"]
        deadline = time.time() + PIPELINE_TIMEOUT
        while time.time() < deadline:
            detail = cl.get_pipeline(cfg["project"], pid)
            if detail.get("status") in _TERMINAL:
                break
            time.sleep(8)
        else:
            pytest.fail("pipeline did not finish in time")
        collect_pipeline_results(db, cl, cfg["project"], pid, "E2E integration run")

    # the schede now carry the REAL run status, and no duplicate was created
    for tc in ("TC-GL-100", "TC-GL-101"):
        t = db.query(models.Test).filter_by(id=tc).first()
        assert t.status == "pass", f"{tc} status={t.status}"
        assert db.query(models.Test).filter_by(external_key=tc).count() == 1


def test_push_roundtrip_and_conflict(db):
    intg = _integration(db, "gl-e2e-2")
    gitlab_sync.sync_integration(db, intg)
    t = db.query(models.Test).filter_by(id="TC-GL-100").first()
    original_body = t.source_body
    api_base, project = parse_gitlab_repo(REPO, f"{GL_WEB}/api/v4")

    try:
        # edit in ThoroTest → push → the file on git reflects it, no status field
        t.title = "Edited by integration test"
        db.commit()
        gitlab_sync.push_test(db, intg, t)
        with GitLabClient(api_base, TOKEN) as gl:
            content = gl.get_file(project, LOGIN_YML, "main")
        assert "Edited by integration test" in content
        assert "status:" not in content

        # diverge the file out-of-band → next push must 409 (PushConflict)
        with GitLabClient(api_base, TOKEN) as gl:
            gl.write_file(project, LOGIN_YML, content + "\n# out-of-band\n", "main",
                          "diverge", update=True)
        t.title = "Edited again"
        db.commit()
        with pytest.raises(git_push.PushConflict):
            gitlab_sync.push_test(db, intg, t)
    finally:
        # restore the fixture so the demo repo is left clean
        with GitLabClient(api_base, TOKEN) as gl:
            cur = gl.get_file_opt(project, LOGIN_YML, "main")
            gl.write_file(project, LOGIN_YML, original_body, "main",
                          "restore fixture", update=cur is not None)
