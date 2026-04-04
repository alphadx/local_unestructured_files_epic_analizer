from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, status

from app.models.schemas import JobProgress, ScanRequest
from app.services import job_manager

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobProgress, status_code=202)
async def start_scan(request: ScanRequest, background_tasks: BackgroundTasks) -> JobProgress:
    """
    Kick off a new analysis job for the specified directory path.

    The job runs in the background; poll ``GET /api/jobs/{job_id}`` for status.
    """
    job_id = job_manager.create_job()
    background_tasks.add_task(job_manager.run_pipeline, job_id, request)
    return job_manager.get_job(job_id)  # type: ignore[return-value]


@router.get("", response_model=list[JobProgress])
async def list_jobs() -> list[JobProgress]:
    return job_manager.list_jobs()


@router.get("/{job_id}", response_model=JobProgress)
async def get_job(job_id: str) -> JobProgress:
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/logs", response_model=list[str])
async def get_job_logs(job_id: str) -> list[str]:
    """Return the timestamped in-memory log for a job (all entries since creation)."""
    if job_manager.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_manager.get_logs(job_id)


@router.websocket("/{job_id}/logs/ws")
async def job_log_websocket(job_id: str, websocket: WebSocket) -> None:
    if job_manager.get_job(job_id) is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue()
    job_manager.subscribe_job_logs(job_id, queue)

    try:
        for line in job_manager.get_logs(job_id):
            await websocket.send_text(line)

        while True:
            entry = await queue.get()
            await websocket.send_text(entry)
    except WebSocketDisconnect:
        pass
    finally:
        job_manager.unsubscribe_job_logs(job_id, queue)
