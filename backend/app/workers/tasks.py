from __future__ import annotations

"""
Celery tasks for the analysis pipeline.

The pipeline code is async; Celery tasks are sync callables.

To avoid cross-loop errors with SQLAlchemy async + asyncpg pooled connections,
we keep one event loop per worker process and run all task coroutines there.
"""

import asyncio
import logging
from typing import Any

from celery.signals import worker_process_shutdown

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    """Return a persistent event loop scoped to the current Celery worker process."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop


def _run_in_worker_loop(coro: Any) -> Any:
    """Execute *coro* on the worker loop and return its result."""
    loop = _get_worker_loop()
    return loop.run_until_complete(coro)


@worker_process_shutdown.connect
def _close_worker_loop(**_: Any) -> None:
    """Dispose async resources and close the persistent worker loop."""
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        return

    try:
        from app.db.session import dispose_engine

        _worker_loop.run_until_complete(dispose_engine())
    except Exception:
        logger.exception("Failed to dispose async DB engine on worker shutdown")
    finally:
        _worker_loop.close()
        _worker_loop = None


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_analysis_pipeline",
    max_retries=0,  # Pipeline failures are recorded in DB; no auto-retry.
)
def run_analysis_pipeline(self, job_id: str, request_data: dict) -> None:
    """Execute the full analysis pipeline for *job_id* in the worker event loop."""
    try:
        _run_in_worker_loop(_async_pipeline(job_id, request_data))
    except Exception as exc:
        logger.exception("Celery task failed for job %s", job_id)
        # Best-effort: mark the job as failed in the DB.
        try:
            _run_in_worker_loop(_mark_job_failed(job_id, repr(exc)))
        except Exception:
            pass
        raise


async def _async_pipeline(job_id: str, request_data: dict) -> None:
    """Run the pipeline within a managed DB session and Redis connection."""
    from app.db.session import AsyncSessionLocal
    from app.models.schemas import ScanRequest
    from app.services import job_manager

    request = ScanRequest(**request_data)

    async with AsyncSessionLocal() as db:
        await job_manager.run_pipeline(job_id, request, db=db)


async def _mark_job_failed(job_id: str, error: str) -> None:
    from sqlalchemy import update as sa_update

    from app.db.models import Job
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Job)
            .where(Job.job_id == job_id)
            .values(status="failed", error_message=error, message="Error durante el análisis.")
        )
        await db.commit()
