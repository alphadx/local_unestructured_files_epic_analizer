from __future__ import annotations

"""
Celery tasks for the analysis pipeline.

The pipeline code is async; we bridge it using ``asyncio.run()``, which
creates a fresh event loop for the duration of each task.  This is safe
because Celery workers are plain OS processes, not running an existing loop.
"""

import asyncio
import logging
import shutil
from typing import Callable

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_analysis_pipeline",
    max_retries=0,  # Pipeline failures are recorded in DB; no auto-retry.
)
def run_analysis_pipeline(self, job_id: str, request_data: dict) -> None:
    """Execute the full analysis pipeline for *job_id* inside a fresh event loop."""
    try:
        asyncio.run(_async_pipeline(job_id, request_data))
    except Exception as exc:
        logger.exception("Celery task failed for job %s", job_id)
        # Best-effort: mark the job as failed in the DB.
        try:
            asyncio.run(_mark_job_failed(job_id, repr(exc)))
        except Exception:
            pass
        raise


async def _async_pipeline(job_id: str, request_data: dict) -> None:
    """Run the pipeline within a managed DB session and Redis connection."""
    from app.db.session import AsyncSessionLocal
    from app.models.schemas import ScanRequest
    from app.services import job_manager

    request = ScanRequest(**request_data)

    async with AsyncSessionLocal() as db:
        await job_manager.run_pipeline(job_id, request, db=db)


async def _mark_job_failed(job_id: str, error: str) -> None:
    from sqlalchemy import update as sa_update

    from app.db.models import Job
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(Job)
            .where(Job.job_id == job_id)
            .values(status="failed", error_message=error, message="Error durante el análisis.")
        )
        await db.commit()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_dedup_worker",
    max_retries=0,
)
def run_dedup_worker(self, job_id: str, backend: str = "jdupes") -> dict:
    """
    Background deduplication worker — Phase 5B.

    Runs an external deduplication tool (jdupes, rmlint, czkawka, or native SHA-256)
    over the files indexed by *job_id* and returns a summary of duplicate groups found.

    This task is **independent** of the main analysis pipeline: it can be dispatched
    before, after, or in parallel with ``run_analysis_pipeline``.

    Args:
        job_id:  The UUID of an already-completed analysis job whose scanned files
                 will be used as input.
        backend: Deduplication backend to use.
                 - ``"jdupes"``  — fast exact-duplicate finder via jdupes CLI.
                 - ``"rmlint"``  — checksumming deduplicator with sh script output.
                 - ``"czkawka"`` — similar-image/video detector.
                 - ``"native"``  — pure SHA-256 (no external binary required).

    Returns:
        dict with keys:
            job_id, backend, duplicates_found, groups, status, error (on failure).
    """
    logger.info("run_dedup_worker: starting for job=%s backend=%s", job_id, backend)
    try:
        result = _run_dedup_sync(job_id, backend)
        logger.info(
            "run_dedup_worker: completed for job=%s — duplicates_found=%d",
            job_id, result.get("duplicates_found", 0),
        )
        return result
    except Exception as exc:
        logger.exception("run_dedup_worker: failed for job=%s", job_id)
        return {
            "job_id": job_id,
            "backend": backend,
            "duplicates_found": 0,
            "groups": [],
            "status": "failed",
            "error": repr(exc),
        }


def _run_dedup_sync(job_id: str, backend: str) -> dict:
    """Synchronous deduplication logic for the Celery worker."""
    import subprocess
    import tempfile
    from pathlib import Path

    # Retrieve the list of scanned file paths from the job report
    file_paths = asyncio.run(_fetch_job_file_paths(job_id))

    if not file_paths:
        return {
            "job_id": job_id,
            "backend": backend,
            "duplicates_found": 0,
            "groups": [],
            "status": "completed",
        }

    if backend == "native":
        groups = _native_dedup(file_paths)
    elif backend == "jdupes":
        groups = _run_with_fallback("jdupes", _jdupes_dedup, file_paths)
    elif backend == "rmlint":
        groups = _run_with_fallback("rmlint", _rmlint_dedup, file_paths)
    elif backend == "czkawka":
        # Delegate to DedupService for czkawka
        from app.models.schemas import FileIndex
        from app.services.dedup_service import DedupService

        fi_list = [
            FileIndex(
                path=p, name=Path(p).name, extension=Path(p).suffix.lower(),
                size_bytes=0, created_at="", modified_at="", sha256="",
            )
            for p in file_paths
            if Path(p).exists()
        ]
        svc = DedupService(backend="czkawka")
        updated = svc.find_duplicates(fi_list)
        dup_of_map: dict[str, list[str]] = {}
        for fi in updated:
            if fi.is_duplicate and fi.duplicate_of:
                if fi.duplicate_of not in dup_of_map:
                    dup_of_map[fi.duplicate_of] = [fi.duplicate_of]
                dup_of_map[fi.duplicate_of].append(fi.path)
        groups = [{"original": orig, "duplicates": dups} for orig, dups in dup_of_map.items()]
    else:
        logger.warning("run_dedup_worker: unknown backend '%s', using native", backend)
        groups = _native_dedup(file_paths)

    return {
        "job_id": job_id,
        "backend": backend,
        "duplicates_found": sum(len(g.get("duplicates", [])) - 1 for g in groups),
        "groups": groups,
        "status": "completed",
    }


async def _fetch_job_file_paths(job_id: str) -> list[str]:
    """Retrieve all file paths indexed by a job from the database."""
    from app.db.session import AsyncSessionLocal
    from app.services import job_manager

    async with AsyncSessionLocal() as db:
        report = await job_manager.get_report(db, job_id)
        if report is None:
            return []
        # Collect paths from duplicate_groups (covers all scanned files)
        paths: list[str] = []
        seen: set[str] = set()
        for group in report.duplicate_groups:
            for p in group.files:
                if p not in seen:
                    seen.add(p)
                    paths.append(p)
        return paths


def _run_with_fallback(
    tool_name: str,
    tool_fn: "Callable[[list[str]], list[dict]]",
    file_paths: list[str],
) -> list[dict]:
    """
    Run *tool_fn* if *tool_name* is available on PATH; otherwise fall back to native SHA-256.
    """
    if shutil.which(tool_name):
        return tool_fn(file_paths)
    logger.warning(
        "run_dedup_worker: '%s' not found on PATH, falling back to native SHA-256 deduplication.",
        tool_name,
    )
    return _native_dedup(file_paths)


def _native_dedup(file_paths: list[str]) -> list[dict]:
    """Pure-Python SHA-256 deduplication — no external tools required."""
    import hashlib
    from pathlib import Path

    hash_map: dict[str, list[str]] = {}
    for p in file_paths:
        path = Path(p)
        if not path.is_file():
            continue
        try:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            digest = h.hexdigest()
            hash_map.setdefault(digest, []).append(p)
        except OSError:
            continue

    return [
        {"sha256": digest, "original": paths[0], "duplicates": paths}
        for digest, paths in hash_map.items()
        if len(paths) > 1
    ]


def _jdupes_dedup(file_paths: list[str]) -> list[dict]:
    """Run jdupes on the unique parent directories of the provided file paths."""
    import json
    import subprocess
    from pathlib import Path

    dirs = sorted({str(Path(p).parent) for p in file_paths if Path(p).exists()})
    if not dirs:
        return []

    try:
        result = subprocess.run(
            ["jdupes", "--recurse", "--json", *dirs],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode not in (0, 1):
            logger.warning("jdupes exited with %d: %s", result.returncode, result.stderr[:300])
            return _native_dedup(file_paths)

        data = json.loads(result.stdout)
        groups: list[dict] = []
        for match_set in data.get("matchSets", []):
            files = [f["filePath"] for f in match_set.get("fileList", [])]
            if len(files) > 1:
                groups.append({"original": files[0], "duplicates": files})
        return groups

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        logger.warning("jdupes failed (%s), falling back to native", exc)
        return _native_dedup(file_paths)


def _rmlint_dedup(file_paths: list[str]) -> list[dict]:
    """Run rmlint on the parent directories and parse its JSON output."""
    import json
    import subprocess
    from pathlib import Path

    dirs = sorted({str(Path(p).parent) for p in file_paths if Path(p).exists()})
    if not dirs:
        return []

    try:
        result = subprocess.run(
            ["rmlint", "--output", "json:-", *dirs],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode not in (0, 1):
            logger.warning("rmlint exited with %d: %s", result.returncode, result.stderr[:300])
            return _native_dedup(file_paths)

        data = json.loads(result.stdout)
        # rmlint JSON: list of {type, path, ...}; originals have type "duplicate_dir"/"unfinished_cksum"
        # duplicates have type "duplicate_file"
        original_map: dict[str, str] = {}  # checksum -> original path
        dup_map: dict[str, list[str]] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            etype = entry.get("type", "")
            path = entry.get("path", "")
            checksum = entry.get("checksum", path)
            if etype in ("unfinished_cksum", "original"):
                original_map[checksum] = path
                dup_map.setdefault(checksum, [path])
            elif etype == "duplicate_file":
                dup_map.setdefault(checksum, []).append(path)

        return [
            {"sha256": cs, "original": original_map.get(cs, paths[0]), "duplicates": paths}
            for cs, paths in dup_map.items()
            if len(paths) > 1
        ]

    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        logger.warning("rmlint failed (%s), falling back to native", exc)
        return _native_dedup(file_paths)
