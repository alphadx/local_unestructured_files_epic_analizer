from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException

from app.models.schemas import ClusterSummary, DataHealthReport, DocumentMetadata, JobStatistics
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


@router.get("/{job_id}/statistics", response_model=JobStatistics)
async def get_statistics(job_id: str) -> JobStatistics:
    """
    Return detailed distribution statistics for a completed analysis job.

    Includes breakdown by file extension, document category, PII risk level,
    and a summary of each semantic cluster with its inconsistency count.
    """
    report = job_manager.get_report(job_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Statistics not available. Job may still be running or does not exist.",
        )

    documents = job_manager.get_documents(job_id)

    extension_breakdown: dict[str, int] = dict(
        Counter(
            doc.file_index.extension or "(sin extensión)"
            for doc in documents
        )
    )
    category_distribution: dict[str, int] = dict(
        Counter(doc.categoria.value for doc in documents)
    )
    pii_risk_distribution: dict[str, int] = dict(
        Counter(doc.pii_info.risk_level.value for doc in documents)
    )
    cluster_summary = [
        ClusterSummary(
            cluster_id=c.cluster_id,
            label=c.label,
            document_count=c.document_count,
            inconsistency_count=len(c.inconsistencies),
        )
        for c in report.clusters
    ]

    return JobStatistics(
        job_id=job_id,
        total_files=report.total_files,
        unique_files=report.total_files - report.duplicates,
        duplicate_files=report.duplicates,
        extension_breakdown=extension_breakdown,
        category_distribution=category_distribution,
        pii_risk_distribution=pii_risk_distribution,
        cluster_summary=cluster_summary,
    )
