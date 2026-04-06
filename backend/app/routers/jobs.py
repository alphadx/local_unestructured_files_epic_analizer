from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.schemas import JobProgress, ScanRequest
from app.services import job_manager
from app.workers.tasks import run_analysis_pipeline

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobProgress, status_code=202)
async def start_scan(request: ScanRequest, db: AsyncSession = Depends(get_db)) -> JobProgress:
    """
    Kick off a new analysis job. Dispatches to Celery worker.
    Poll ``GET /api/jobs/{job_id}`` for status.
    """
    job_id = await job_manager.create_job(db)
    run_analysis_pipeline.delay(job_id, request.model_dump(mode="json"))
    return await job_manager.get_job(db, job_id)  # type: ignore[return-value]


@router.get("", response_model=list[JobProgress])
async def list_jobs(db: AsyncSession = Depends(get_db)) -> list[JobProgress]:
    return await job_manager.list_jobs(db)


@router.get("/{job_id}", response_model=JobProgress)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> JobProgress:
    job = await job_manager.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/logs", response_model=list[str])
async def get_job_logs(job_id: str, db: AsyncSession = Depends(get_db)) -> list[str]:
    """Return the full log history for a job from the database."""
    if await job_manager.get_job(db, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return await job_manager.get_logs(db, job_id)


@router.websocket("/{job_id}/logs/ws")
async def job_log_websocket(job_id: str, websocket: WebSocket) -> None:
    """
    Stream live log entries for a running job via WebSocket.

    Replays historical logs first, then subscribes to Redis pub/sub for
    real-time entries published by the Celery worker.
    """
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        if await job_manager.get_job(db, job_id) is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()

        # Replay existing logs
        historical = await job_manager.get_logs(db, job_id)
        for line in historical:
            await websocket.send_text(line)

    # Subscribe to Redis pub/sub for real-time entries
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"job:{job_id}:logs")

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(f"job:{job_id}:logs")
        await pubsub.close()
        await redis_client.aclose()


@router.post("/prune", status_code=200)
async def prune_jobs(db: AsyncSession = Depends(get_db)) -> dict:
    """Manually trigger job pruning based on the configured retention policy."""
    pruned = await job_manager.prune_old_jobs(db)
    return {"pruned": pruned}
