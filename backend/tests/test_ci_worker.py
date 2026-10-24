from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import sessionmaker

from backend import models
from backend import ci_worker
from backend.routers import ci as ci_router


def _job(job_id="job-1"):
    now = datetime.now(timezone.utc).isoformat()
    return models.CIJob(
        id=job_id,
        integration_id="int-1",
        provider="github",
        workflow="ci.yml",
        ref="main",
        status="queued",
        queue_status="queued",
        started_at=now,
        updated_at=now,
    )


def _patch_sessions(db, monkeypatch):
    sessions = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(ci_worker, "SessionLocal", sessions)
    return sessions


def test_claim_is_exclusive_and_finish_is_persistent(db, monkeypatch):
    sessions = _patch_sessions(db, monkeypatch)
    db.add(_job())
    db.commit()

    assert ci_worker.claim_next("worker-a") == "job-1"
    assert ci_worker.claim_next("worker-b") is None
    assert ci_worker.renew_lease("job-1", "worker-b") is False
    assert ci_worker.renew_lease("job-1", "worker-a") is True

    ci_worker.finish_job("job-1", "worker-a")
    check = sessions()
    try:
        job = check.query(models.CIJob).filter_by(id="job-1").one()
        assert job.queue_status == "done"
        assert job.status == "done"
        assert job.lease_until is None
        assert job.attempts == 1
    finally:
        check.close()


def test_expired_lease_is_recovered_by_another_worker(db, monkeypatch):
    sessions = _patch_sessions(db, monkeypatch)
    job = _job("job-recover")
    job.queue_status = "processing"
    job.worker_id = "dead-worker"
    job.lease_until = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    job.attempts = 1
    db.add(job)
    db.commit()

    assert ci_worker.claim_next("worker-b") == "job-recover"
    check = sessions()
    try:
        recovered = check.query(models.CIJob).filter_by(id="job-recover").one()
        assert recovered.worker_id == "worker-b"
        assert recovered.attempts == 2
        assert recovered.queue_status == "processing"
    finally:
        check.close()


def test_processing_job_without_lease_is_recovered(db, monkeypatch):
    _patch_sessions(db, monkeypatch)
    job = _job("job-null-lease")
    job.queue_status = "processing"
    job.worker_id = "dead-worker"
    job.lease_until = None
    db.add(job)
    db.commit()

    assert ci_worker.claim_next("worker-b") == "job-null-lease"


def test_recovered_job_rejects_updates_from_old_worker(db, monkeypatch):
    sessions = _patch_sessions(db, monkeypatch)
    monkeypatch.setattr(ci_router, "SessionLocal", sessions)
    job = _job("job-fenced")
    job.queue_status = "processing"
    job.status = "running"
    job.worker_id = "worker-new"
    db.add(job)
    db.commit()

    with pytest.raises(ci_router.LostJobLease):
        ci_router._update_job(
            "job-fenced", worker_id="worker-old", status="done"
        )

    db.expire_all()
    assert db.query(models.CIJob).filter_by(id="job-fenced").one().status == "running"


def test_terminal_job_cleanup_respects_ttl(db, monkeypatch):
    _patch_sessions(db, monkeypatch)
    old = _job("job-old")
    old.queue_status = "done"
    old.status = "done"
    old.updated_at = (
        datetime.now(timezone.utc) - timedelta(days=2)
    ).isoformat()
    recent = _job("job-recent")
    recent.queue_status = "done"
    recent.status = "done"
    db.add_all([old, recent])
    db.commit()

    assert ci_worker.cleanup_expired_jobs() == 1
    assert db.query(models.CIJob).filter_by(id="job-old").first() is None
    assert db.query(models.CIJob).filter_by(id="job-recent").first() is not None
