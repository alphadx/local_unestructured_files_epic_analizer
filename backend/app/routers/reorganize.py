from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import DataHealthReport
from app.services import job_manager

router = APIRouter(prefix="/api/reorganize", tags=["reorganize"])


@router.post("/{job_id}/execute")
async def execute_reorganization(job_id: str) -> dict:
    """
    Execute the reorganisation plan suggested by the analysis.

    **SAFETY**: files are only *moved* after the user explicitly calls this
    endpoint.  The scan itself is always read-only.

    Returns a summary of moved files.
    """
    report = job_manager.get_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    import os
    import shutil
    from pathlib import Path

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
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(src), "error": str(exc)})

    return {
        "job_id": job_id,
        "moved": len(moved),
        "errors": len(errors),
        "details": moved,
        "error_details": errors,
    }
