from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from app.services.audit_log import AuditEntry, get_all, total_count

router = APIRouter(prefix="/api/audit", tags=["audit"])


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


@router.get("")
async def list_audit_entries(
    operation: str | None = Query(default=None, description="Filter by operation name"),
    resource_type: str | None = Query(default=None, description="Filter by resource type"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """
    Return the immutable audit log.

    Entries are returned newest-first. The log records key operations:
    job creation, completion, failure, reorganization, and search queries.
    """
    entries = get_all(
        operation=operation,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total_count(),
        "offset": offset,
        "limit": limit,
        "entries": [_entry_to_dict(e) for e in entries],
    }
