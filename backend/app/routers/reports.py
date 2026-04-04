from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import DataHealthReport, DocumentMetadata
from app.services import job_manager

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{job_id}", response_model=DataHealthReport)
async def get_report(job_id: str) -> DataHealthReport:
    """Return the full health report for a completed job."""
    report = job_manager.get_report(job_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found. Job may still be running or does not exist.",
        )
    return report


@router.get("/{job_id}/documents", response_model=list[DocumentMetadata])
async def get_documents(job_id: str) -> list[DocumentMetadata]:
    """Return the list of classified documents for a job."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_manager.get_documents(job_id)
