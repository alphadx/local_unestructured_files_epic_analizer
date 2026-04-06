from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.audit_log import AuditEntry, get_all_async, total_count_async

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
    operation: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entries = await get_all_async(db, operation=operation, resource_type=resource_type, limit=limit, offset=offset)
    total = await total_count_async(db)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [_entry_to_dict(e) for e in entries],
    }
