from __future__ import annotations

"""
In-memory job store + async pipeline runner.

Jobs are identified by a UUID and stored in a plain dict.
For a production deployment this would be replaced by a proper task queue
(Celery / ARQ), but for the MVP in-memory is sufficient.
"""

import asyncio
import logging
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

# job_id -> JobProgress
_jobs: dict[str, JobProgress] = {}
# job_id -> DataHealthReport (once completed)
_reports: dict[str, DataHealthReport] = {}
# job_id -> list[DocumentMetadata]
_documents: dict[str, list[DocumentMetadata]] = {}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobProgress(job_id=job_id, status=JobStatus.PENDING)
    return job_id


def get_job(job_id: str) -> JobProgress | None:
    return _jobs.get(job_id)


def get_report(job_id: str) -> DataHealthReport | None:
    return _reports.get(job_id)


def get_documents(job_id: str) -> list[DocumentMetadata]:
    return _documents.get(job_id, [])


def list_jobs() -> list[JobProgress]:
    return list(_jobs.values())


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(job_id: str, request: ScanRequest) -> None:
    """Full async pipeline: scan → classify → embed → cluster → report."""
    job = _jobs[job_id]
    job.status = JobStatus.RUNNING
    job.message = "Iniciando escaneo…"

    try:
        # --- Step 1: Fast local indexing ---
        from app.services.scanner import scan_directory

        loop = asyncio.get_running_loop()
        file_indices = await loop.run_in_executor(None, scan_directory, request.path)

        job.total_files = len(file_indices)
        job.message = f"Indexados {len(file_indices)} archivos. Filtrando duplicados…"

        unique_files = [f for f in file_indices if not f.is_duplicate]
        logger.info(
            "Job %s: %d total, %d unique", job_id, len(file_indices), len(unique_files)
        )

        # --- Step 2: Gemini classification ---
        from app.services import gemini_service

        documents: list[DocumentMetadata] = []

        for idx, fi in enumerate(unique_files):
            job.processed_files = idx + 1
            job.message = f"Clasificando ({idx + 1}/{len(unique_files)}): {fi.name}"

            doc = await loop.run_in_executor(None, gemini_service.classify_document, fi)

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

        # --- Step 4: Clustering ---
        clusters = []
        if request.enable_clustering and documents:
            job.message = "Construyendo clusters semánticos…"
            from app.services.clustering_service import build_clusters, detect_inconsistencies
            from app.db import vector_store

            chroma_data: list[dict] = []
            if request.enable_embeddings:
                chroma_data = await loop.run_in_executor(None, vector_store.get_all_embeddings)

            clusters = await loop.run_in_executor(
                None, build_clusters, documents, chroma_data
            )
            clusters = await loop.run_in_executor(
                None, detect_inconsistencies, clusters, documents
            )

        # --- Step 5: Build health report ---
        job.message = "Generando reporte de salud de datos…"
        report = _build_report(job_id, file_indices, documents, clusters)
        _reports[job_id] = report

        job.status = JobStatus.COMPLETED
        job.message = "Análisis completado."
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Job %s failed", job_id)
        job.status = JobStatus.FAILED
        # Use repr() to include the exception type in addition to its message,
        # providing more context for debugging without exposing internal stack traces.
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
