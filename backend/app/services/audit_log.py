from __future__ import annotations

"""
Persistent audit log backed by PostgreSQL.

Entries are written to the ``audit_log`` table via an async SQLAlchemy session.
The public API mirrors the previous in-memory implementation so callers require
minimal changes.

Sync wrapper ``record`` keeps backward compatibility for call-sites that run
outside of an async context (e.g. synchronous background functions that call
``asyncio.run()`` internally).
"""

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as db_models


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    timestamp: str
    operation: str
    actor: str
    resource_id: str | None
    resource_type: str | None
    details: dict[str, Any]
    outcome: str


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------


async def record_async(
    db: AsyncSession,
    operation: str,
    *,
    actor: str = "system",
    resource_id: str | None = None,
    resource_type: str | None = None,
    outcome: str = "success",
    **details: Any,
) -> AuditEntry:
    """Persist an audit entry and return it."""
    from datetime import datetime, timezone

    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db_entry = db_models.AuditEntry(
        entry_id=entry_id,
        timestamp=now,
        operation=operation,
        actor=actor,
        resource_id=resource_id,
        resource_type=resource_type,
        details=dict(details),
        outcome=outcome,
    )
    db.add(db_entry)
    await db.commit()

    return AuditEntry(
        entry_id=entry_id,
        timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        operation=operation,
        actor=actor,
        resource_id=resource_id,
        resource_type=resource_type,
        details=dict(details),
        outcome=outcome,
    )


async def get_all_async(
    db: AsyncSession,
    *,
    operation: str | None = None,
    resource_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[AuditEntry]:
    """Return audit entries matching optional filters, newest first."""
    stmt = select(db_models.AuditEntry).order_by(db_models.AuditEntry.timestamp.desc())
    if operation:
        stmt = stmt.where(db_models.AuditEntry.operation == operation)
    if resource_type:
        stmt = stmt.where(db_models.AuditEntry.resource_type == resource_type)
    stmt = stmt.offset(offset).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        AuditEntry(
            entry_id=r.entry_id,
            timestamp=r.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            operation=r.operation,
            actor=r.actor,
            resource_id=r.resource_id,
            resource_type=r.resource_type,
            details=r.details or {},
            outcome=r.outcome,
        )
        for r in rows
    ]


async def total_count_async(db: AsyncSession) -> int:
    from sqlalchemy import func, select as sa_select

    result = await db.execute(sa_select(func.count()).select_from(db_models.AuditEntry))
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Sync shims (backward compatibility for non-async call-sites)
# ---------------------------------------------------------------------------


def record(
    operation: str,
    *,
    actor: str = "system",
    resource_id: str | None = None,
    resource_type: str | None = None,
    outcome: str = "success",
    **details: Any,
) -> AuditEntry:
    """Fire-and-forget audit record.  Uses the current running loop if available,
    otherwise falls back to asyncio.run() for callers in sync contexts."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Schedule as a background coroutine without awaiting.
        loop.create_task(
            _record_in_background(
                operation,
                actor=actor,
                resource_id=resource_id,
                resource_type=resource_type,
                outcome=outcome,
                **details,
            )
        )
        # Return a placeholder so callers that inspect the return value still work.
        return AuditEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=_now_iso(),
            operation=operation,
            actor=actor,
            resource_id=resource_id,
            resource_type=resource_type,
            details=dict(details),
            outcome=outcome,
        )
    else:
        return asyncio.run(
            _record_in_background(
                operation,
                actor=actor,
                resource_id=resource_id,
                resource_type=resource_type,
                outcome=outcome,
                **details,
            )
        )


async def _record_in_background(operation: str, **kwargs: Any) -> AuditEntry:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await record_async(db, operation, **kwargs)


def get_all(
    *,
    operation: str | None = None,
    resource_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[AuditEntry]:
    """Sync wrapper around get_all_async (used by legacy endpoints)."""
    from app.db.session import AsyncSessionLocal

    async def _inner() -> list[AuditEntry]:
        async with AsyncSessionLocal() as db:
            return await get_all_async(db, operation=operation, resource_type=resource_type, limit=limit, offset=offset)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Cannot call asyncio.run() inside a running loop.
        # Return empty list — callers should prefer the async version.
        return []
    return asyncio.run(_inner())


def total_count() -> int:
    from app.db.session import AsyncSessionLocal

    async def _inner() -> int:
        async with AsyncSessionLocal() as db:
            return await total_count_async(db)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        return 0
    return asyncio.run(_inner())

