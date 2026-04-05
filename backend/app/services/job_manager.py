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
from functools import partial
from typing import Any

from app.models.schemas import (
    DataHealthReport,
    DocumentCategory,
    DocumentMetadata,
    DocumentChunk,
    DuplicateGroup,
    GroupAnalysisResult,
    GroupMode,
    JobProgress,
    JobStatus,
    ScanRequest,
    SourceProvider,
)
from app.services.source_service import (
    cleanup_source_path,
    prepare_scan_source,
    rewrite_remote_paths,
)

logger = logging.getLogger(__name__)

_SCAN_TIMEOUT_SECONDS = 300  # 5-minute hard limit for the filesystem scan

# job_id -> JobProgress
_jobs: dict[str, JobProgress] = {}
# job_id -> DataHealthReport (once completed)
_reports: dict[str, DataHealthReport] = {}
# job_id -> list[DocumentMetadata]
_documents: dict[str, list[DocumentMetadata]] = {}
# job_id -> list[DocumentChunk]
_chunks: dict[str, list[DocumentChunk]] = {}
# job_id -> list of timestamped log lines
_job_logs: dict[str, list[str]] = {}
# job_id -> active websocket subscriber queues for live logs
_log_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
# job_id -> GroupAnalysisResult (once completed)
_group_analysis: dict[str, GroupAnalysisResult] = {}


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


def get_chunks(job_id: str) -> list[DocumentChunk]:
    return _chunks.get(job_id, [])


def get_group_analysis(job_id: str) -> GroupAnalysisResult | None:
    return _group_analysis.get(job_id)


def store_group_analysis(job_id: str, analysis: GroupAnalysisResult) -> None:
    _group_analysis[job_id] = analysis


def get_logs(job_id: str) -> list[str]:
    return _job_logs.get(job_id, [])


def subscribe_job_logs(job_id: str, queue: asyncio.Queue[str]) -> None:
    _log_subscribers[job_id].append(queue)


def unsubscribe_job_logs(job_id: str, queue: asyncio.Queue[str]) -> None:
    queues = _log_subscribers.get(job_id)
    if not queues:
        return
    try:
        queues.remove(queue)
    except ValueError:
        pass
    if not queues:
        _log_subscribers.pop(job_id, None)


def list_jobs() -> list[JobProgress]:
    return list(_jobs.values())


def _log(job_id: str, level: str, msg: str) -> None:
    """Append a timestamped entry to the in-memory job log and emit to the Python logger."""
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] [{level}] {msg}"
    _job_logs.setdefault(job_id, []).append(entry)
    for queue in list(_log_subscribers.get(job_id, [])):
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            # If the frontend isn't keeping up, drop the oldest queued message.
            continue
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
        scan_root = request.path
        temp_scan_root = None

        if request.source_provider != SourceProvider.LOCAL:
            scan_root, temp_scan_root = prepare_scan_source(request)

        _log(job_id, "INFO", f"[Paso 1/5] Escaneando directorio '{scan_root}'…")
        t0 = time.monotonic()
        try:
            file_indices = await asyncio.wait_for(
                loop.run_in_executor(None, scan_directory, scan_root),
                timeout=_SCAN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"El escaneo de '{request.path}' superó el límite de "
                f"{_SCAN_TIMEOUT_SECONDS}s. ¿La ruta es una red lenta o un volumen muy grande?"
            )
        elapsed = time.monotonic() - t0

        if temp_scan_root and request.source_options.get("_remote_prefix"):
            file_indices = rewrite_remote_paths(
                file_indices,
                temp_scan_root,
                request.source_options["_remote_prefix"],
            )

        job.total_files = len(file_indices)
        unique_files = [f for f in file_indices if not f.is_duplicate]
        dups = len(file_indices) - len(unique_files)

        _log(job_id, "INFO",
             f"[Paso 1/5] Escaneo completado en {elapsed:.1f}s — "
             f"total={len(file_indices)}, únicos={len(unique_files)}, duplicados={dups}")
        job.message = f"Indexados {len(file_indices)} archivos. Filtrando duplicados…"

        # --- Step 2: Gemini classification ---
        from app.services import gemini_service
        from app.services.document_extraction_service import (
            build_classification_context,
            extract_document_content,
        )

        _log(job_id, "INFO", f"[Paso 2/5] Clasificando {len(unique_files)} archivo(s) con Gemini…")
        documents: list[DocumentMetadata] = []
        chunks: list[DocumentChunk] = []

        for idx, fi in enumerate(unique_files):
            job.processed_files = idx + 1
            job.message = f"Clasificando ({idx + 1}/{len(unique_files)}): {fi.name}"
            _log(job_id, "DEBUG", f"Clasificando [{idx + 1}/{len(unique_files)}]: {fi.path}")

            extraction = await loop.run_in_executor(None, extract_document_content, fi)
            _log(
                job_id,
                "DEBUG",
                f"  → extracción={extraction.extraction_method}, partes={len(extraction.chunks)}",
            )

            classification_context = build_classification_context(extraction)
            if classification_context:
                _log(
                    job_id,
                    "DEBUG",
                    f"  → contexto LLM={len(classification_context)} caracteres",
                )

            doc = await loop.run_in_executor(
                None,
                gemini_service.classify_document,
                fi,
                classification_context or extraction.text,
            )
            _log(job_id, "DEBUG",
                 f"  → categoría={doc.categoria}, pii={doc.pii_info.detected}")
            chunks.extend(extraction.chunks)

            # --- Step 3: Embeddings ---
            if request.enable_embeddings:
                from app.services import embeddings_service
                from app.db import vector_store

                embed_text = _build_embedding_text(doc, extraction.text)
                if embed_text:
                    embedding = await loop.run_in_executor(
                        None, embeddings_service.embed_text, embed_text
                    )
                    doc.embedding = embedding
                    await loop.run_in_executor(
                        None,
                        partial(vector_store.upsert_document, doc, job_id=job_id),
                    )

                    for chunk in extraction.chunks:
                        chunk_text = _build_chunk_embedding_text(chunk.text)
                        if not chunk_text:
                            continue
                        chunk.embedding = await loop.run_in_executor(
                            None, embeddings_service.embed_text, chunk_text
                        )
                        await loop.run_in_executor(
                            None,
                            partial(
                                vector_store.upsert_chunk,
                                chunk,
                                job_id=job_id,
                                category=doc.categoria.value,
                                cluster_sugerido=doc.analisis_semantico.cluster_sugerido or "",
                                risk_level=doc.pii_info.risk_level.value,
                                confidence=doc.analisis_semantico.confianza_clasificacion or 0.0,
                            ),
                        )

            documents.append(doc)

        _documents[job_id] = documents
        _chunks[job_id] = chunks
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
                chroma_data = await loop.run_in_executor(
                    None, vector_store.get_all_embeddings, "chunk"
                )
                if not chroma_data:
                    chroma_data = await loop.run_in_executor(
                        None, vector_store.get_all_embeddings, "document"
                    )
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
        _log(job_id, "INFO", "[Paso 4/6] Generando reporte de salud de datos…")
        report = _build_report(job_id, file_indices, documents, clusters)
        _reports[job_id] = report

        # --- Step 5: Group analysis ---
        if documents:
            job.message = "Analizando grupos de directorio…"
            _log(job_id, "INFO", "[Paso 5/6] Analizando grupos de directorio…")
            from app.services.grouping_service import analyze_all_groups

            group_analysis = await loop.run_in_executor(
                None,
                analyze_all_groups,
                job_id,
                documents,
                GroupMode.STRICT,
                10,
            )
            store_group_analysis(job_id, group_analysis)
            _log(job_id, "INFO", f"[Paso 5/6] Group analysis completado — {group_analysis.group_count} grupos")
        else:
            _log(job_id, "INFO", "[Paso 5/6] No hay documentos para análisis de grupos")

        job.status = JobStatus.COMPLETED
        job.message = "Análisis completado."
        _log(job_id, "INFO", f"[Paso 6/6] Job {job_id} completado exitosamente ✓")

    except Exception as exc:  # noqa: BLE001
        _log(job_id, "ERROR", f"Job {job_id} falló: {exc!r}")
        logger.exception("Job %s failed", job_id)
        job.status = JobStatus.FAILED
        job.error = repr(exc)
        job.message = "Error durante el análisis."
    finally:
        if temp_scan_root:
            cleanup_source_path(temp_scan_root)


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


def _build_embedding_text(doc: DocumentMetadata, extracted_text: str | None) -> str:
    directory_context = " ".join(
        [
            doc.file_index.path,
            doc.file_index.name,
            doc.file_index.extension,
            doc.file_index.mime_type or "",
        ]
    )

    parts = [
        doc.analisis_semantico.resumen,
        " ".join(doc.analisis_semantico.palabras_clave),
        doc.categoria.value,
        directory_context,
        extracted_text[:4_000] if extracted_text else None,
    ]
    return " ".join(part for part in parts if part).strip()


def _build_chunk_embedding_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""
    return cleaned[:4_000]
