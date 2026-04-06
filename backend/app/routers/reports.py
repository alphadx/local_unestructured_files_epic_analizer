from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.models.schemas import (
    ContactsReport,
    CorpusExplorationReport,
    DataHealthReport,
    DocumentChunk,
    DocumentMetadata,
    GroupAnalysisResult,
    GroupSimilarityResponse,
    JobStatistics,
    NamedEntityType,
    ScanComparisonResponse,
)
from app.services.analytics_service import build_corpus_exploration, build_job_statistics
from app.services.compare_service import compare_scans
from app.services.executive_summary_service import (
    build_executive_summary_text,
    render_summary_pdf,
)
from app.services.export_service import documents_to_csv, documents_to_json_payload
from app.services.ner_service import build_contacts_report
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


@router.get("/{job_id}/export/json")
async def export_documents_json(job_id: str) -> JSONResponse:
    """Export full document inventory as JSON."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    documents = job_manager.get_documents(job_id)
    payload = {
        "job_id": job_id,
        "total_documents": len(documents),
        "documents": documents_to_json_payload(documents),
    }
    return JSONResponse(content=payload)


@router.get("/{job_id}/export/csv")
async def export_documents_csv(job_id: str) -> PlainTextResponse:
    """Export full document inventory as CSV."""
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    documents = job_manager.get_documents(job_id)
    csv_content = documents_to_csv(documents)

    headers = {
        "Content-Disposition": f'attachment; filename="inventory_{job_id}.csv"'
    }
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers=headers,
    )


@router.get("/{base_job_id}/compare/{target_job_id}", response_model=ScanComparisonResponse)
async def compare_job_scans(
    base_job_id: str,
    target_job_id: str,
    include_unchanged: bool = Query(
        default=False,
        description="Include unchanged files in response.",
    ),
    limit: int = Query(
        default=200,
        ge=1,
        le=2000,
        description="Maximum number of items returned per change bucket.",
    ),
) -> ScanComparisonResponse:
    """Compare two completed scans and detect new/modified/deleted files."""
    if job_manager.get_job(base_job_id) is None:
        raise HTTPException(status_code=404, detail=f"Base job {base_job_id} not found")
    if job_manager.get_job(target_job_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Target job {target_job_id} not found"
        )

    base_documents = job_manager.get_documents(base_job_id)
    target_documents = job_manager.get_documents(target_job_id)

    return compare_scans(
        base_job_id=base_job_id,
        target_job_id=target_job_id,
        base_documents=base_documents,
        target_documents=target_documents,
        include_unchanged=include_unchanged,
        limit=limit,
    )


@router.get("/{job_id}/contacts", response_model=ContactsReport)
async def get_contacts(
    job_id: str,
    entity_type: NamedEntityType | None = Query(
        default=None,
        description="Filter results by entity type (e.g. PERSON, ORGANIZATION, EMAIL).",
    ),
    min_frequency: int = Query(
        default=1,
        ge=1,
        description="Only include contacts that appear at least this many times.",
    ),
) -> ContactsReport:
    """
    Return aggregated named entities (contacts) extracted from all documents in a job.

    Entities are extracted via a hybrid NER pipeline:
    - Layer 1 (regex): emails, Chilean RUTs, phone numbers — always present.
    - Layer 2 (Gemini): persons, organizations, locations, dates, money amounts
      (available when documents were classified with Gemini).

    Results are sorted by frequency (most common first).
    Use `entity_type` to narrow results to a specific type and `min_frequency`
    to filter out rare mentions.
    """
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    documents = job_manager.get_documents(job_id)
    report = build_contacts_report(job_id, documents)

    if entity_type is not None or min_frequency > 1:
        report.contacts = [
            c
            for c in report.contacts
            if (entity_type is None or c.entity_type == entity_type)
            and c.frequency >= min_frequency
        ]

    return report


@router.get("/{job_id}/executive-summary/pdf")
async def get_executive_summary_pdf(
    job_id: str,
    use_gemini: bool = Query(
        default=True,
        description="If true, tries to refine summary text with Gemini.",
    ),
) -> Response:
    """Generate and download an executive summary PDF for a completed job."""
    report = job_manager.get_report(job_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Report not found. Job may still be running or does not exist.",
        )

    documents = job_manager.get_documents(job_id)
    summary_text = build_executive_summary_text(
        job_id=job_id,
        report=report,
        documents=documents,
        use_gemini=use_gemini,
    )
    pdf_bytes = render_summary_pdf(summary_text)

    headers = {
        "Content-Disposition": f'attachment; filename="executive_summary_{job_id}.pdf"'
    }
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )
