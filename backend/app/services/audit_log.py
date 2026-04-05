from __future__ import annotations

"""
Append-only in-memory audit log.

Each entry records *who* triggered *what* operation and its outcome.
The log is intentionally immutable: entries are never deleted or modified
(though the list will be cleared on process restart — for true persistence
use PostgreSQL in a future milestone).
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    timestamp: str
    operation: str
    actor: str
    resource_id: str | None
    resource_type: str | None
    details: dict[str, Any]
    outcome: str  # "success" | "failure" | "started"


_audit_log: list[AuditEntry] = []


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def record(
    operation: str,
    *,
    actor: str = "system",
    resource_id: str | None = None,
    resource_type: str | None = None,
    outcome: str = "success",
    **details: Any,
) -> AuditEntry:
    """Append an immutable audit entry and return it."""
    entry = AuditEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=_now_iso(),
        operation=operation,
        actor=actor,
        resource_id=resource_id,
        resource_type=resource_type,
        details=dict(details),
        outcome=outcome,
    )
    _audit_log.append(entry)
    return entry


def get_all(
    *,
    operation: str | None = None,
    resource_type: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[AuditEntry]:
    """Return entries matching optional filters, newest first."""
    entries = list(reversed(_audit_log))
    if operation:
        entries = [e for e in entries if e.operation == operation]
    if resource_type:
        entries = [e for e in entries if e.resource_type == resource_type]
    return entries[offset : offset + limit]


def total_count() -> int:
    return len(_audit_log)
