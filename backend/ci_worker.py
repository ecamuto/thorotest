"""Durable, multi-worker-safe executor for CI and synchronization jobs."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_

from . import models
from .db import SessionLocal
from .observability import ci_job_outcome
from .observability import redact
from .runtime_state import runtime_state


logger = logging.getLogger("thorotest.ci_worker")
LEASE_SECONDS = 90
HEARTBEAT_SECONDS = 30
POLL_SECONDS = 1.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def claim_next(worker_id: str) -> str | None:
    """Atomically claim one queued or abandoned job for this worker."""
    db = SessionLocal()
    try:
        now = _iso(_now())
        candidates = (
            db.query(models.CIJob.id, models.CIJob.queue_status, models.CIJob.lease_until)
            .filter(
                or_(
                    models.CIJob.queue_status == "queued",
                    and_(
                        models.CIJob.queue_status == "processing",
                        or_(
                            models.CIJob.lease_until.is_(None),
                            models.CIJob.lease_until < now,
                        ),
                    ),
                )
            )
            .order_by(models.CIJob.started_at)
            .limit(10)
            .all()
        )
        lease = _iso(_now() + timedelta(seconds=LEASE_SECONDS))
        for job_id, queue_status, old_lease in candidates:
            query = db.query(models.CIJob).filter(
                models.CIJob.id == job_id,
                models.CIJob.queue_status == queue_status,
            )
            if queue_status == "processing":
                query = query.filter(models.CIJob.lease_until == old_lease)
            claimed = query.update(
                {
                    models.CIJob.queue_status: "processing",
                    models.CIJob.worker_id: worker_id,
                    models.CIJob.lease_until: lease,
                    models.CIJob.attempts: models.CIJob.attempts + 1,
                    models.CIJob.updated_at: now,
                },
                synchronize_session=False,
            )
            db.commit()
            if claimed == 1:
                return job_id
        return None
    finally:
        db.close()


def renew_lease(job_id: str, worker_id: str) -> bool:
    db = SessionLocal()
    try:
        updated = (
            db.query(models.CIJob)
            .filter(
                models.CIJob.id == job_id,
                models.CIJob.queue_status == "processing",
                models.CIJob.worker_id == worker_id,
            )
            .update(
                {
                    models.CIJob.lease_until: _iso(
                        _now() + timedelta(seconds=LEASE_SECONDS)
                    ),
                    models.CIJob.updated_at: _iso(_now()),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return updated == 1
    finally:
        db.close()


def finish_job(job_id: str, worker_id: str, *, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.query(models.CIJob).filter(models.CIJob.id == job_id).first()
        if not job or job.worker_id != worker_id:
            return
        job.queue_status = "error" if error else "done"
        job.status = "error" if error else "done"
        job.error = redact(error) if error else None
        job.lease_until = None
        job.updated_at = _iso(_now())
        provider = job.provider
        db.commit()
        ci_job_outcome(provider, "error" if error else "done")
    finally:
        db.close()


def cleanup_expired_jobs() -> int:
    cutoff = _iso(_now() - timedelta(seconds=runtime_state.settings.job_ttl_seconds))
    db = SessionLocal()
    try:
        deleted = (
            db.query(models.CIJob)
            .filter(
                models.CIJob.queue_status.in_(("done", "error")),
                models.CIJob.updated_at < cutoff,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted
    finally:
        db.close()


class CIJobWorker:
    def __init__(self) -> None:
        self.worker_id = uuid.uuid4().hex
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if os.getenv("CI_WORKER_ENABLED", "1").strip().lower() not in (
            "1", "true", "yes",
        ):
            return
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="thorotest-ci-worker")

    async def close(self) -> None:
        self._stop.set()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _execute(self, job_id: str) -> None:
        from .routers.ci import execute_job

        work = asyncio.create_task(
            asyncio.to_thread(execute_job, job_id, self.worker_id)
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {work}, timeout=HEARTBEAT_SECONDS
                )
                if done:
                    error = work.exception()
                    if error:
                        logger.error(
                            "Provider job %s failed (%s)", job_id, type(error).__name__
                        )
                    finish_job(
                        job_id,
                        self.worker_id,
                        error=str(error) if error else None,
                    )
                    return
                renewed = await asyncio.to_thread(
                    renew_lease, job_id, self.worker_id
                )
                if not renewed:
                    logger.error("Lost lease for provider job %s", job_id)
                    return
        finally:
            if not work.done():
                # Provider calls are synchronous and cannot be force-cancelled;
                # the expired lease lets another worker recover after shutdown.
                work.cancel()

    async def _run(self) -> None:
        cleanup_tick = 0
        while not self._stop.is_set():
            try:
                job_id = await asyncio.to_thread(claim_next, self.worker_id)
                if job_id:
                    await self._execute(job_id)
                    continue
                cleanup_tick += 1
                if cleanup_tick >= 300:
                    await asyncio.to_thread(cleanup_expired_jobs)
                    cleanup_tick = 0
                await asyncio.sleep(POLL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("CI worker loop failed (%s)", type(exc).__name__)
                await asyncio.sleep(min(POLL_SECONDS * 5, 10))


ci_job_worker = CIJobWorker()
