"""GitHub Actions collection logic (no network — fake client / crafted zip)."""
import io
import zipfile
from datetime import datetime, timedelta, timezone

from backend import models
from backend.github_actions import (
    extract_junit_from_zip, pick_dispatched_run, collect_run_results,
)


def _zip_with(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_junit_merges_suites():
    z = _zip_with({
        "a.xml": b'<testsuite name="s1"><testcase name="t1" classname="pkg.A"/></testsuite>',
        "b.xml": b'<testsuites><testsuite name="s2"><testcase name="t2" classname="pkg.B"/></testsuite></testsuites>',
        "notes.txt": b"ignore me",
    })
    merged = extract_junit_from_zip(z)
    assert b"t1" in merged and b"t2" in merged
    assert merged.count(b"<testcase") == 2       # both cases carried over
    assert merged.count(b'name="s1"') == 1 and merged.count(b'name="s2"') == 1


def test_pick_dispatched_run_newest_after_since():
    since = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
    runs = [
        {"id": 1, "created_at": "2026-07-08T11:00:00Z"},   # before → ignored
        {"id": 2, "created_at": "2026-07-08T12:00:05Z"},
        {"id": 3, "created_at": "2026-07-08T12:00:30Z"},   # newest after
    ]
    assert pick_dispatched_run(runs, since)["id"] == 3


def test_pick_dispatched_run_none_when_all_stale():
    since = datetime.now(timezone.utc) + timedelta(hours=1)
    assert pick_dispatched_run([{"id": 1, "created_at": "2026-07-08T12:00:00Z"}], since) is None


class _FakeClient:
    def __init__(self, artifacts, zip_bytes):
        self._artifacts = artifacts
        self._zip = zip_bytes

    def list_artifacts(self, owner, repo, run_id):
        return self._artifacts

    def download_artifact_zip(self, owner, repo, artifact_id):
        assert artifact_id == 99
        return self._zip


def test_collect_run_results_imports_junit(db):
    z = _zip_with({"junit.xml": (
        b'<testsuites name="run"><testsuite name="e2e">'
        b'<testcase name="login works" classname="e2e.auth"/>'
        b'<testcase name="checkout fails" classname="e2e.checkout"><failure/></testcase>'
        b'</testsuite></testsuites>'
    )})
    client = _FakeClient([{"id": 99, "name": "junit"}], z)
    stats = collect_run_results(db, client, "org", "repo", 555, "junit", "CI #555")
    assert stats["tests"] == 2 and stats["runs"] == 1

    run = db.query(models.Run).filter(models.Run.name == "CI #555").first()
    assert run is not None
    assert run.passed == 1 and run.failed == 1


def test_collect_falls_back_to_first_artifact_when_name_missing(db):
    z = _zip_with({"results.xml": b'<testsuite name="s"><testcase name="t" classname="c"/></testsuite>'})
    client = _FakeClient([{"id": 99, "name": "something-else"}], z)
    stats = collect_run_results(db, client, "org", "repo", 1, "junit", None)
    assert stats["tests"] == 1


def test_ci_run_rejects_non_github_integration(client, db):
    db.add(models.Integration(id="int-x", name="Weird", type="vcs_ci",
                              config={"repo_url": "https://example.com/not/github"}))
    db.commit()
    r = client.post("/api/integrations/int-x/ci/run", json={})
    assert r.status_code == 400


def test_ci_run_404_for_missing_integration(client):
    r = client.post("/api/integrations/nope/ci/run", json={})
    assert r.status_code == 404
