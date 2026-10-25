from sqlalchemy.orm import sessionmaker

from backend import models
from backend.ci_worker import finish_job
from backend.routers import ci, integrations


def _shared_sessions(db, monkeypatch):
    factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr(ci, "SessionLocal", factory)
    monkeypatch.setattr("backend.db.SessionLocal", factory)
    monkeypatch.setattr("backend.ci_worker.SessionLocal", factory)


def test_durable_sync_job_executes_and_records_result(client, db, monkeypatch):
    _shared_sessions(db, monkeypatch)
    db.add(models.Integration(
        id="int-provider-job",
        name="GitHub",
        type="vcs_ci",
        config={"repo_url": "https://github.com/acme/web", "branch": "main"},
    ))
    db.commit()

    response = client.post("/api/integrations/int-provider-job/sync")
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = db.query(models.CIJob).filter_by(id=job_id).one()
    job.queue_status = "processing"
    job.worker_id = "worker-1"
    db.commit()

    monkeypatch.setattr(
        integrations,
        "sync_integration",
        lambda session, intg: (
            setattr(intg, "last_sync", "2026-10-25T12:00:00+00:00")
            or {"files": 2, "created": 1, "updated": 1, "skipped": 0}
        ),
    )

    ci.execute_job(job_id, "worker-1")
    finish_job(job_id, "worker-1")
    db.expire_all()

    completed = db.query(models.CIJob).filter_by(id=job_id).one()
    assert completed.queue_status == "done"
    assert completed.result == {
        "last_sync": "2026-10-25T12:00:00+00:00",
        "files": 2,
        "created": 1,
        "updated": 1,
        "skipped": 0,
    }
    assert completed.attempts == 0


def test_repeated_sync_request_coalesces_active_job(client, db):
    db.add(models.Integration(
        id="int-provider-coalesce",
        name="GitHub",
        type="vcs_ci",
        config={"repo_url": "https://github.com/acme/web", "branch": "main"},
    ))
    db.commit()
    first = client.post("/api/integrations/int-provider-coalesce/sync")
    second = client.post("/api/integrations/int-provider-coalesce/sync")
    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert db.query(models.CIJob).filter_by(
        integration_id="int-provider-coalesce",
        job_type="integration_sync",
    ).count() == 1


def test_sync_job_failure_marks_integration_and_job_error(client, db, monkeypatch):
    _shared_sessions(db, monkeypatch)
    db.add(models.Integration(
        id="int-provider-fail",
        name="GitHub",
        type="vcs_ci",
        config={"repo_url": "https://github.com/acme/web", "branch": "main"},
    ))
    db.commit()
    job_id = client.post("/api/integrations/int-provider-fail/sync").json()["job_id"]
    job = db.query(models.CIJob).filter_by(id=job_id).one()
    job.queue_status = "processing"
    job.worker_id = "worker-2"
    db.commit()

    def fail(*_args):
        raise RuntimeError("provider https://user:secret-value@example.test rejected")

    monkeypatch.setattr(integrations, "sync_integration", fail)
    try:
        ci.execute_job(job_id, "worker-2")
    except RuntimeError as exc:
        finish_job(job_id, "worker-2", error=str(exc))

    db.expire_all()
    completed = db.query(models.CIJob).filter_by(id=job_id).one()
    integration = db.query(models.Integration).filter_by(id="int-provider-fail").one()
    assert completed.queue_status == "error"
    assert "secret-value" not in completed.error
    assert integration.status == "error"
