from __future__ import annotations

"""
In-memory job store + async pipeline runner.

Jobs are identified by a UUID and stored in a plain dict.
For a production deployment this would be replaced by a proper task queue
(Celery / ARQ), but for the MVP in-memory is sufficient.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from typing import Any

from app.models.schemas import (
    DataHealthReport,
    DocumentCategory,
    DocumentMetadata,
    DuplicateGroup,
    JobProgress,
    JobStatus,
    ScanRequest,
)

logger = logging.getLogger(__name__)

_SCAN_TIMEOUT_SECONDS = 300  # 5-minute hard limit for the filesystem scan

# job_id -> JobProgress
_jobs: dict[str, JobProgress] = {}
# job_id -> DataHealthReport (once completed)
_reports: dict[str, DataHealthReport] = {}
# job_id -> list[DocumentMetadata]
_documents: dict[str, list[DocumentMetadata]] = {}
# job_id -> list of timestamped log lines
_job_logs: dict[str, list[str]] = {}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobProgress(job_id=job_id, status=JobStatus.PENDING)
    _job_logs[job_id] = []
    return job_id


def get_job(job_id: str) -> JobProgress | None:
    return _jobs.get(job_id)


def get_report(job_id: str) -> DataHealthReport | None:
    return _reports.get(job_id)


def get_documents(job_id: str) -> list[DocumentMetadata]:
    return _documents.get(job_id, [])


def get_logs(job_id: str) -> list[str]:
    return _job_logs.get(job_id, [])


def list_jobs() -> list[JobProgress]:
    return list(_jobs.values())


def _log(job_id: str, level: str, msg: str) -> None:
    """Append a timestamped entry to the in-memory job log and emit to the Python logger."""
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] [{level}] {msg}"
    _job_logs.setdefault(job_id, []).append(entry)
    getattr(logger, level.lower(), logger.info)(msg)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(job_id: str, request: ScanRequest) -> None:
    """Full async pipeline: scan → classify → embed → cluster → report."""
    job = _jobs[job_id]
    job.status = JobStatus.RUNNING
    job.message = "Iniciando escaneo…"

    _log(job_id, "INFO", f"Pipeline iniciado para job {job_id}")
    _log(job_id, "INFO", f"Ruta a escanear: '{request.path}'")
    _log(job_id, "INFO", f"Opciones — embeddings={request.enable_embeddings}, clustering={request.enable_clustering}, pii={request.enable_pii_detection}")

    try:
        # --- Step 1: Fast local indexing ---
        from app.services.scanner import scan_directory

        loop = asyncio.get_running_loop()

        _log(job_id, "INFO", f"[Paso 1/5] Escaneando directorio '{request.path}'…")
        t0 = time.monotonic()
        try:
            file_indices = await asyncio.wait_for(
                loop.run_in_executor(None, scan_directory, request.path),
                timeout=_SCAN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"El escaneo de '{request.path}' superó el límite de "
                f"{_SCAN_TIMEOUT_SECONDS}s. ¿La ruta es una red lenta o un volumen muy grande?"
            )
        elapsed = time.monotonic() - t0

        job.total_files = len(file_indices)
        unique_files = [f for f in file_indices if not f.is_duplicate]
        dups = len(file_indices) - len(unique_files)

        _log(job_id, "INFO",
             f"[Paso 1/5] Escaneo completado en {elapsed:.1f}s — "
             f"total={len(file_indices)}, únicos={len(unique_files)}, duplicados={dups}")
        job.message = f"Indexados {len(file_indices)} archivos. Filtrando duplicados…"

        # --- Step 2: Gemini classification ---
        from app.services import gemini_service

        _log(job_id, "INFO", f"[Paso 2/5] Clasificando {len(unique_files)} archivo(s) con Gemini…")
        documents: list[DocumentMetadata] = []

        for idx, fi in enumerate(unique_files):
            job.processed_files = idx + 1
            job.message = f"Clasificando ({idx + 1}/{len(unique_files)}): {fi.name}"
            _log(job_id, "DEBUG", f"Clasificando [{idx + 1}/{len(unique_files)}]: {fi.path}")

            doc = await loop.run_in_executor(None, gemini_service.classify_document, fi)
            _log(job_id, "DEBUG",
                 f"  → categoría={doc.categoria}, pii={doc.pii_info.detected}")

            # --- Step 3: Embeddings ---
            if request.enable_embeddings:
                from app.services import embeddings_service
                from app.db import vector_store

                embed_text = " ".join(
                    filter(
                        None,
                        [
                            doc.analisis_semantico.resumen,
                            " ".join(doc.analisis_semantico.palabras_clave),
                        ],
                    )
                )
                if embed_text:
                    embedding = await loop.run_in_executor(
                        None, embeddings_service.embed_text, embed_text
                    )
                    doc.embedding = embedding
                    await loop.run_in_executor(None, vector_store.upsert_document, doc)

            documents.append(doc)

        _documents[job_id] = documents
        _log(job_id, "INFO",
             f"[Paso 2/5] Clasificación completada — {len(documents)} documento(s) procesados")

        # --- Step 4: Clustering ---
        clusters = []
        if request.enable_clustering and documents:
            job.message = "Construyendo clusters semánticos…"
            _log(job_id, "INFO", "[Paso 3/5] Construyendo clusters semánticos…")
            from app.services.clustering_service import build_clusters, detect_inconsistencies
            from app.db import vector_store

            chroma_data: list[dict] = []
            if request.enable_embeddings:
                chroma_data = await loop.run_in_executor(None, vector_store.get_all_embeddings)
                _log(job_id, "DEBUG", f"  → {len(chroma_data)} embeddings recuperados de ChromaDB")

            clusters = await loop.run_in_executor(
                None, build_clusters, documents, chroma_data
            )
            clusters = await loop.run_in_executor(
                None, detect_inconsistencies, clusters, documents
            )
            _log(job_id, "INFO", f"[Paso 3/5] Clustering completado — {len(clusters)} cluster(s)")
        else:
            _log(job_id, "INFO", "[Paso 3/5] Clustering omitido (deshabilitado o sin documentos)")

        # --- Step 5: Build health report ---
        job.message = "Generando reporte de salud de datos…"
        _log(job_id, "INFO", "[Paso 4/5] Generando reporte de salud de datos…")
        report = _build_report(job_id, file_indices, documents, clusters)
        _reports[job_id] = report

        job.status = JobStatus.COMPLETED
        job.message = "Análisis completado."
        _log(job_id, "INFO", f"[Paso 5/5] Job {job_id} completado exitosamente ✓")

    except Exception as exc:  # noqa: BLE001
        _log(job_id, "ERROR", f"Job {job_id} falló: {exc!r}")
        logger.exception("Job %s failed", job_id)
        job.status = JobStatus.FAILED
        job.error = repr(exc)
        job.message = "Error durante el análisis."


def _build_report(
    job_id: str,
    file_indices: list[Any],
    documents: list[DocumentMetadata],
    clusters: list[Any],
) -> DataHealthReport:
    # Duplicate groups
    hash_to_paths: dict[str, list[str]] = defaultdict(list)
    for fi in file_indices:
        if fi.sha256:
            hash_to_paths[fi.sha256].append(fi.path)
    dup_groups = [
        DuplicateGroup(sha256=h, files=paths)
        for h, paths in hash_to_paths.items()
        if len(paths) > 1
    ]

    pii_count = sum(1 for d in documents if d.pii_info.detected)
    uncategorised = sum(
        1 for d in documents if d.categoria == DocumentCategory.UNKNOWN
    )

    # Consistency errors aggregated
    all_errors: list[str] = []
    for cl in clusters:
        all_errors.extend(cl.inconsistencies)

    # Reorganisation plan
    reorg_plan: list[dict] = []
    for cl in clusters:
        if cl.label != "Sin_Cluster":
            for item in cl.documents:
                reorg_plan.append(
                    {
                        "documento_id": item.documento_id,
                        "current_path": item.path,
                        "suggested_path": f"/Empresa/Organizado/{cl.label}/{item.documento_id[:8]}",
                        "cluster": cl.label,
                    }
                )

    return DataHealthReport(
        job_id=job_id,
        total_files=len(file_indices),
        duplicates=sum(1 for fi in file_indices if fi.is_duplicate),
        duplicate_groups=dup_groups,
        pii_files=pii_count,
        uncategorised_files=uncategorised,
        consistency_errors=all_errors,
        clusters=clusters,
        reorganisation_plan=reorg_plan,
    )
