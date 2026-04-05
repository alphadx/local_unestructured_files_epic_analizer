from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    CorpusExplorationReport,
    DataHealthReport,
    DocumentChunk,
    DocumentMetadata,
    GroupAnalysisResult,
    GroupSimilarityResponse,
    JobStatistics,
)
from app.services.analytics_service import build_corpus_exploration, build_job_statistics
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


@router.get("/{job_id}/chunks", response_model=list[DocumentChunk])
async def get_chunks(job_id: str) -> list[DocumentChunk]:
    """Return the extracted semantic chunks for a job."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_manager.get_chunks(job_id)


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
    return build_job_statistics(job_id, report, documents)


@router.get("/{job_id}/exploration", response_model=CorpusExplorationReport)
async def get_exploration(job_id: str) -> CorpusExplorationReport:
    """Return corpus exploration metrics and pattern summaries."""
    report = job_manager.get_report(job_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Exploration not available. Job may still be running or does not exist.",
        )

    documents = job_manager.get_documents(job_id)
    return build_corpus_exploration(job_id, report, documents)


@router.get("/{job_id}/groups", response_model=GroupAnalysisResult)
async def get_groups(job_id: str) -> GroupAnalysisResult:
    """
    Return the directory group analysis for a completed job.

    Includes all detected groups with their feature profiles, health scores,
    and top k similarities between groups.
    """
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    analysis = job_manager.get_group_analysis(job_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Group analysis not available. Job may still be running or does not exist.",
        )

    return analysis


@router.get(
    "/{job_id}/groups/{group_id}/similarity", response_model=GroupSimilarityResponse
)
async def get_group_similarity(job_id: str, group_id: str) -> GroupSimilarityResponse:
    """
    Return similar groups for a given group.

    Filters the computed similarities to show only those involving the specified group,
    ranked by composite similarity score.
    """
    analysis = job_manager.get_group_analysis(job_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Group analysis not available.",
        )

    # Find the group profile
    group_profile = next((g for g in analysis.groups if g.group_id == group_id), None)
    if group_profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"Group {group_id} not found in job {job_id}.",
        )

    # Filter similarities to include only this group
    relevant_similarities = [
        s
        for s in analysis.group_similarities
        if s.group_a_id == group_id or s.group_b_id == group_id
    ]

    # Sort by composite score
    relevant_similarities.sort(key=lambda x: x.composite_score, reverse=True)

    return GroupSimilarityResponse(
        group_id=group_id,
        group_path=group_profile.group_path,
        job_id=job_id,
        similar_groups=relevant_similarities,
    )
