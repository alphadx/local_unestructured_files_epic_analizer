from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import audit_log, job_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reorganize", tags=["reorganize"])


@router.post("/{job_id}/execute")
async def execute_reorganization(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Execute the reorganisation plan suggested by the analysis.

    **SAFETY**: files are only *moved* after the user explicitly calls this
    endpoint.  The scan itself is always read-only.

    Returns a summary of moved files.
    """
    report = await job_manager.get_report(db, job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    moved: list[dict] = []
    errors: list[dict] = []

    for action in report.reorganisation_plan:
        src = Path(action["current_path"])
        dst = Path(action["suggested_path"])
        if not src.exists():
            errors.append({"path": str(src), "error": "Source file not found"})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved.append({"from": str(src), "to": str(dst)})
        except OSError as exc:
            # Log the full exception server-side; return a safe generic message
            logger.error("Failed to move %s to %s: %s", src, dst, exc)
            errors.append({"path": str(src), "error": "File move operation failed"})

    audit_log.record(
        "reorganization.executed",
        resource_id=job_id,
        resource_type="job",
        outcome="success" if not errors else "failure",
        moved=len(moved),
        errors=len(errors),
    )

    return {
        "job_id": job_id,
        "moved": len(moved),
        "errors": len(errors),
        "details": moved,
        "error_details": errors,
    }
