from __future__ import annotations

"""
Celery tasks for the analysis pipeline.

The pipeline code is async; we bridge it using ``asyncio.run()``, which
creates a fresh event loop for the duration of each task.  This is safe
because Celery workers are plain OS processes, not running an existing loop.
"""

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_analysis_pipeline",
    max_retries=0,  # Pipeline failures are recorded in DB; no auto-retry.
)
def run_analysis_pipeline(self, job_id: str, request_data: dict) -> None:
    """Execute the full analysis pipeline for *job_id* inside a fresh event loop."""
    try:
        asyncio.run(_async_pipeline(job_id, request_data))
    except Exception as exc:
        logger.exception("Celery task failed for job %s", job_id)
        # Best-effort: mark the job as failed in the DB.
        try:
            asyncio.run(_mark_job_failed(job_id, repr(exc)))
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
