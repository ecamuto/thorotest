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
                     status="running", commit="abc1234", branch="main", when="just now")
    p = db.query(models.Pipeline).filter_by(id=pid).first()
    assert p is not None and p.status == "running" and p.platform == "gitlab"
    assert p.commit == "abc1234" and p.duration is None

    # completion: same id updated in place, no duplicate
    _upsert_pipeline(db, pid, status="fail", duration=_fmt_duration(252))
    assert db.query(models.Pipeline).filter_by(id=pid).count() == 1
    p = db.query(models.Pipeline).filter_by(id=pid).first()
    assert p.status == "fail"
    assert p.duration == "4m 12s"
    # None fields don't clobber existing values
    assert p.name == "GitLab pipeline #42"
    assert p.commit == "abc1234"
