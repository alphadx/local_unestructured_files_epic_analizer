from __future__ import annotations

from fastapi import APIRouter, Query

from app.config import settings
from app.models.schemas import FilterConfiguration
from app.services.audit_log import AuditEntry, get_all

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _entry_to_dict(entry: AuditEntry) -> dict:
    return {
        "entry_id": entry.entry_id,
        "timestamp": entry.timestamp,
        "operation": entry.operation,
        "actor": entry.actor,
        "resource_id": entry.resource_id,
        "resource_type": entry.resource_type,
        "outcome": entry.outcome,
        "details": entry.details,
    }


@router.get("/filter-stats")
async def get_filter_stats(
    job_id: str | None = Query(default=None, description="Filter by specific job ID"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    Return statistics about filtered files from recent scans.

    Retrieves entries from the audit log where files were excluded by
    MIME type or extension filtering rules during ingestion.

    Query parameters:
    - job_id: Optional filter to get stats for a specific job
    - limit: Maximum number of entries to return (default 100, max 1000)
    - offset: Pagination offset (default 0)

    Returns:
        {
            "total_scans_with_filters": int,
            "total_files_filtered": int,
            "scans": [
                {
                    "job_id": str,
                    "timestamp": str (ISO8601),
                    "skipped_count": int,
                    "skipped_files": [{"path": str, "reason": str}, ...],
                    "entry_id": str,
                }
            ]
        }
    """
    # Fetch all scan.files_filtered audit entries, newest first
    entries = get_all(
        operation="scan.files_filtered",
        resource_type="job",
        limit=limit + offset,  # Get extra to account for offset
        offset=0,
    )

    # Filter by job_id if provided
    if job_id:
        entries = [e for e in entries if e.resource_id == job_id]

    # Apply offset for pagination
    entries = entries[offset : offset + limit]

    # Calculate totals
    total_scans_with_filters = len(entries)
    total_files_filtered = sum(e.details.get("skipped_count", 0) for e in entries)

    # Build response
    scans = []
    for entry in entries:
        scans.append({
            "job_id": entry.resource_id,
            "timestamp": entry.timestamp,
            "skipped_count": entry.details.get("skipped_count", 0),
            "skipped_files": entry.details.get("skipped_files", []),
            "entry_id": entry.entry_id,
        })

    return {
        "total_scans_with_filters": total_scans_with_filters,
        "total_files_filtered": total_files_filtered,
        "scans": scans,
    }


@router.get("/filter-config", response_model=FilterConfiguration)
async def get_filter_config() -> FilterConfiguration:
    """
    Return the current system-wide content filtering configuration.

    Returns:
        {
            "ingestion_mode": str,  # "whitelist" or "blacklist"
            "allowed_extensions": str,  # comma-separated list
            "denied_extensions": str,  # comma-separated list
            "allowed_mime_types": str,  # comma-separated list
            "denied_mime_types": str,  # comma-separated list
        }
    """
    return FilterConfiguration(
        ingestion_mode=settings.ingestion_mode,
        allowed_extensions=settings.allowed_extensions,
        denied_extensions=settings.denied_extensions,
        allowed_mime_types=settings.allowed_mime_types,
        denied_mime_types=settings.denied_mime_types,
    )
