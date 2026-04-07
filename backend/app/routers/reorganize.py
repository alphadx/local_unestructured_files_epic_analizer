from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
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


@router.post("/{job_id}/generate-script", response_class=PlainTextResponse)
async def generate_reorganization_script(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """
    Generate a shell script with the reorganisation plan — without executing it.

    The script uses ``mv`` commands with ``mkdir -p`` for safety and can be
    reviewed by an operator before running on the server.

    If ``rmlint`` is available on the system PATH, it is used to produce an
    enhanced script with checksum verification; otherwise a plain ``mv`` script
    is generated.

    Returns a ``text/plain`` response (downloadable as ``reorg_<job_id>.sh``).
    """
    report = await job_manager.get_report(db, job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    now = datetime.now(timezone.utc).isoformat()
    plan = report.reorganisation_plan

    use_rmlint = shutil.which("rmlint") is not None

    if use_rmlint and plan:
        script_content = _generate_rmlint_script(job_id, plan, now)
    else:
        script_content = _generate_native_script(job_id, plan, now, use_rmlint=use_rmlint)

    audit_log.record(
        "reorganization.script_generated",
        resource_id=job_id,
        resource_type="job",
        outcome="success",
        actions=len(plan),
        backend="rmlint" if use_rmlint else "native",
    )

    filename = f"reorg_{job_id[:8]}.sh"
    return PlainTextResponse(
        content=script_content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _generate_native_script(
    job_id: str,
    plan: list[dict],
    timestamp: str,
    *,
    use_rmlint: bool,
) -> str:
    """Build a plain bash mv-based reorganisation script."""
    rmlint_note = (
        "# (rmlint not found on PATH — using plain mv script)\n"
        if not use_rmlint
        else ""
    )

    lines = [
        "#!/bin/bash",
        "# ============================================================",
        f"# Epic Analyzer — Script de reorganización",
        f"# Job ID  : {job_id}",
        f"# Generado: {timestamp}",
        "# ============================================================",
        "# ADVERTENCIA: Revisa este script ANTES de ejecutarlo.",
        "# Los movimientos de archivos son IRREVERSIBLES.",
        "# Ejecuta con: bash reorg_<job_id>.sh",
        "#",
        rmlint_note,
        "set -euo pipefail",
        "",
        f"echo '[Epic Analyzer] Iniciando reorganización ({len(plan)} acción(es))...'",
        "",
    ]

    for i, action in enumerate(plan, start=1):
        src = action.get("current_path", "")
        dst = action.get("suggested_path", "")
        cluster = action.get("cluster", "")
        dst_dir = str(Path(dst).parent) if dst else ""

        lines += [
            f"# Acción {i}/{len(plan)}" + (f" — cluster: {cluster}" if cluster else ""),
            f'if [ -f "{src}" ]; then',
            f'  mkdir -p "{dst_dir}"',
            f'  mv "{src}" "{dst}"',
            f'  echo "  ✓ Movido: {src}"',
            "else",
            f'  echo "  ✗ No encontrado: {src}" >&2',
            "fi",
            "",
        ]

    lines += [
        "echo '[Epic Analyzer] Reorganización completada.'",
    ]
    return "\n".join(lines) + "\n"


def _generate_rmlint_script(job_id: str, plan: list[dict], timestamp: str) -> str:
    """
    Use rmlint to build an enhanced script.

    rmlint is invoked on the source directories involved in the reorganisation
    plan to detect any remaining duplicates, and its output sh script is
    prepended with the Epic Analyzer mv commands.
    """
    source_dirs = sorted({
        str(Path(action["current_path"]).parent)
        for action in plan
        if action.get("current_path")
    })

    rmlint_script = ""
    if source_dirs:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = subprocess.run(
                    ["rmlint", "--output", f"sh:{tmpdir}/rmlint.sh", "--output", "json:-",
                     *source_dirs],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                rmlint_sh = Path(tmpdir) / "rmlint.sh"
                if rmlint_sh.exists():
                    rmlint_script = rmlint_sh.read_text(encoding="utf-8")
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.warning("generate-script: rmlint failed (%s), falling back to native", exc)
            return _generate_native_script(job_id, plan, timestamp, use_rmlint=False)

    header = "\n".join([
        "#!/bin/bash",
        "# ============================================================",
        f"# Epic Analyzer — Script de reorganización (generado con rmlint)",
        f"# Job ID  : {job_id}",
        f"# Generado: {timestamp}",
        "# ============================================================",
        "# ADVERTENCIA: Revisa este script ANTES de ejecutarlo.",
        "#",
        "set -euo pipefail",
        "",
    ])

    mv_block_lines = [
        f"echo '[Epic Analyzer] Aplicando {len(plan)} movimiento(s) planificado(s)...'",
        "",
    ]
    for i, action in enumerate(plan, start=1):
        src = action.get("current_path", "")
        dst = action.get("suggested_path", "")
        dst_dir = str(Path(dst).parent) if dst else ""
        mv_block_lines += [
            f'mkdir -p "{dst_dir}"',
            f'mv "{src}" "{dst}" && echo "  ✓ {i}/{len(plan)}: {src}"',
        ]
    mv_block_lines.append("")
    mv_block_lines.append("echo '[Epic Analyzer] Movimientos completados.'")

    rmlint_section = (
        "\n# --- rmlint: limpieza de duplicados exactos ---\n" + rmlint_script
        if rmlint_script
        else "\n# (rmlint no generó resultado para los directorios indicados)\n"
    )

    return header + "\n".join(mv_block_lines) + rmlint_section + "\n"
