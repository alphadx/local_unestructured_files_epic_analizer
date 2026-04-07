from __future__ import annotations

"""
PostgreSQL-backed job store + async pipeline runner.

All job state is persisted to PostgreSQL via SQLAlchemy async sessions.
Real-time log streaming is provided by Redis pub/sub
(channel ``job:{job_id}:logs``).  The `_log_subscribers` dict is kept
for in-process WebSocket delivery within the FastAPI process.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from functools import partial
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.config import settings
from app.db import models as db_models
from app.db.session import AsyncSessionLocal
from app.services.source_service import (
    cleanup_source_path,
    prepare_scan_source,
    rewrite_remote_paths,
)
from app.services import audit_log

logger = logging.getLogger(__name__)

_SCAN_TIMEOUT_SECONDS = 300  # 5-minute hard limit for the filesystem scan

# job_id -> active websocket subscriber queues for live logs (in-process only)
_log_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)

# ---------------------------------------------------------------------------
# Redis client (module-level, lazily initialised)
# ---------------------------------------------------------------------------

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------


async def _update_job(db: AsyncSession, job_id: str, **fields: Any) -> None:
    """Update scalar and/or extra-dict fields on a Job row."""
    row = await db.get(db_models.Job, job_id)
    if row is None:
        return

    extra_override: dict | None = fields.pop("extra", None)
    extra_merge: dict | None = fields.pop("extra_update", None)

    for key, value in fields.items():
        setattr(row, key, value)

    if extra_override is not None:
        row.extra = extra_override
    if extra_merge is not None:
        merged = dict(row.extra or {})
        merged.update(extra_merge)
        row.extra = merged

    row.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def _load_job_progress(db: AsyncSession, job_id: str) -> JobProgress | None:
    row = await db.get(db_models.Job, job_id)
    if row is None:
        return None
    return _row_to_progress(row)


def _row_to_progress(row: db_models.Job) -> JobProgress:
    extra = row.extra or {}
    return JobProgress(
        job_id=row.job_id,
        status=JobStatus(row.status),
        message=row.message,
        error=row.error_message,
        total_files=extra.get("total_files", 0),
        processed_files=extra.get("processed_files", row.documents_processed or 0),
    )


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


async def create_job(db: AsyncSession) -> str:
    job_id = str(uuid.uuid4())
    row = db_models.Job(job_id=job_id, status="pending")
    db.add(row)
    await db.commit()
    await audit_log.record_async(
        db,
        "job.created",
        resource_id=job_id,
        resource_type="job",
        outcome="started",
    )
    return job_id


async def get_job(db: AsyncSession, job_id: str) -> JobProgress | None:
    row = await db.get(db_models.Job, job_id)
    if row is None:
        return None
    return _row_to_progress(row)


async def get_report(db: AsyncSession, job_id: str) -> DataHealthReport | None:
    row = await db.get(db_models.Report, job_id)
    if row is None:
        return None
    return DataHealthReport.model_validate(row.data)


async def get_documents(db: AsyncSession, job_id: str) -> list[DocumentMetadata]:
    result = await db.execute(
        select(db_models.Document).where(db_models.Document.job_id == job_id)
    )
    return [DocumentMetadata.model_validate(r.data) for r in result.scalars()]


async def get_chunks(db: AsyncSession, job_id: str) -> list[DocumentChunk]:
    result = await db.execute(
        select(db_models.Chunk).where(db_models.Chunk.job_id == job_id)
    )
    return [DocumentChunk.model_validate(r.data) for r in result.scalars()]


async def get_group_analysis(db: AsyncSession, job_id: str) -> GroupAnalysisResult | None:
    row = await db.get(db_models.GroupAnalysis, job_id)
    if row is None:
        return None
    return GroupAnalysisResult.model_validate(row.data)


async def store_group_analysis(db: AsyncSession, job_id: str, analysis: GroupAnalysisResult) -> None:
    row = await db.get(db_models.GroupAnalysis, job_id)
    if row is None:
        row = db_models.GroupAnalysis(job_id=job_id, data=analysis.model_dump())
        db.add(row)
    else:
        row.data = analysis.model_dump()
    await db.commit()


async def get_logs(db: AsyncSession, job_id: str) -> list[str]:
    result = await db.execute(
        select(db_models.JobLog)
        .where(db_models.JobLog.job_id == job_id)
        .order_by(db_models.JobLog.created_at)
    )
    return [r.message for r in result.scalars()]


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


async def list_jobs(db: AsyncSession) -> list[JobProgress]:
    result = await db.execute(select(db_models.Job))
    return [_row_to_progress(r) for r in result.scalars()]


async def prune_old_jobs(db: AsyncSession) -> int:
    """Remove jobs exceeding retention limits. Returns count of pruned jobs."""
    if not settings.max_jobs_retained and not settings.job_max_age_hours:
        return 0

    now = datetime.now(timezone.utc)
    terminal_statuses = (JobStatus.COMPLETED.value, JobStatus.FAILED.value)

    result = await db.execute(
        select(db_models.Job).where(db_models.Job.status.in_(terminal_statuses))
    )
    completed_jobs: list[db_models.Job] = list(result.scalars())

    to_remove: set[str] = set()

    # Age-based pruning
    if settings.job_max_age_hours > 0:
        max_age_secs = settings.job_max_age_hours * 3600
        for job in completed_jobs:
            created = job.created_at
            # Ensure timezone-aware comparison
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (now - created).total_seconds()
            if age > max_age_secs:
                to_remove.add(job.job_id)

    # Count-based pruning (keep the N most recent)
    if settings.max_jobs_retained > 0:
        remaining = [j for j in completed_jobs if j.job_id not in to_remove]
        remaining.sort(key=lambda j: j.created_at)
        excess = len(remaining) - settings.max_jobs_retained
        if excess > 0:
            for j in remaining[:excess]:
                to_remove.add(j.job_id)

    for jid in to_remove:
        await db.execute(
            delete(db_models.Job).where(db_models.Job.job_id == jid)
        )
        await audit_log.record_async(
            db,
            "job.pruned",
            resource_id=jid,
            resource_type="job",
            outcome="success",
        )

    if to_remove:
        await db.commit()

    return len(to_remove)


async def _log(job_id: str, level: str, msg: str, db: AsyncSession) -> None:
    """Persist a log entry to DB, publish to Redis, and push to in-process queues."""
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] [{level}] {msg}"

    # Persist to DB
    db.add(db_models.JobLog(job_id=job_id, message=entry))
    await db.commit()

    # Publish to Redis for cross-process subscribers (e.g. WebSocket in another worker)
    try:
        await _get_redis().publish(f"job:{job_id}:logs", entry)
    except Exception as redis_err:  # noqa: BLE001
        logger.warning("Redis publish failed for job %s: %s", job_id, redis_err)

    # Push to in-process WebSocket queues
    for queue in list(_log_subscribers.get(job_id, [])):
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            continue

    getattr(logger, level.lower(), logger.info)(msg)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(job_id: str, request: ScanRequest, db: AsyncSession) -> None:
    """Full async pipeline: scan → classify → embed → cluster → report."""
    await _update_job(db, job_id, status=JobStatus.RUNNING.value, message="Iniciando escaneo…")

    await _log(job_id, "INFO", f"Pipeline iniciado para job {job_id}", db)
    await _log(job_id, "INFO", f"Ruta a escanear: '{request.path}'", db)
    await _log(job_id, "INFO", f"Opciones — embeddings={request.enable_embeddings}, clustering={request.enable_clustering}, pii={request.enable_pii_detection}", db)

    temp_scan_root = None
    try:
        # --- Step 1: Fast local indexing ---
        from app.services.scanner import scan_directory_with_stats

        loop = asyncio.get_running_loop()
        scan_root = request.path

        if request.source_provider != SourceProvider.LOCAL:
            scan_root, temp_scan_root = prepare_scan_source(request)

        await _log(job_id, "INFO", f"[Paso 1/5] Escaneando directorio '{scan_root}'…", db)
        t0 = time.monotonic()
        try:
            # Use override values if provided, otherwise fall back to system settings
            ingestion_mode = request.ingestion_mode or settings.ingestion_mode
            allowed_extensions = request.allowed_extensions or settings.allowed_extensions
            denied_extensions = request.denied_extensions or settings.denied_extensions
            allowed_mime_types = request.allowed_mime_types or settings.allowed_mime_types
            denied_mime_types = request.denied_mime_types or settings.denied_mime_types

            if request.ingestion_mode or request.allowed_extensions or request.denied_extensions or request.allowed_mime_types or request.denied_mime_types:
                await _log(job_id, "INFO", f"[Sobrescrito] Usando configuración personalizada de filtrado", db)

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    partial(
                        scan_directory_with_stats,
                        ingestion_mode=ingestion_mode,
                        allowed_extensions=allowed_extensions,
                        denied_extensions=denied_extensions,
                        allowed_mime_types=allowed_mime_types,
                        denied_mime_types=denied_mime_types,
                    ),
                    scan_root,
                ),
                timeout=_SCAN_TIMEOUT_SECONDS,
            )
            file_indices, filter_stats = result
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

        # Register filter statistics in audit log
        if filter_stats.get("filters_applied") and filter_stats.get("skipped_by_filter"):
            await audit_log.record_async(
                db,
                "scan.files_filtered",
                actor="system",
                resource_id=job_id,
                resource_type="job",
                outcome="success",
                skipped_count=len(filter_stats["skipped_by_filter"]),
                skipped_files=filter_stats["skipped_by_filter"][:10],  # Store first 10 for brevity
                filters_applied=True,
            )
            await _log(
                job_id,
                "INFO",
                f"Filtrado aplicado: {len(filter_stats['skipped_by_filter'])} archivo(s) excluido(s) por reglas de ingesta.",
                db,
            )

        await _update_job(db, job_id, extra={"total_files": len(file_indices), "processed_files": 0})
        unique_files = [f for f in file_indices if not f.is_duplicate]
        dups = len(file_indices) - len(unique_files)

        await _log(job_id, "INFO",
             f"[Paso 1/5] Escaneo completado en {elapsed:.1f}s — "
             f"total={len(file_indices)}, únicos={len(unique_files)}, duplicados={dups}", db)
        await _update_job(db, job_id, message=f"Indexados {len(file_indices)} archivos. Filtrando duplicados…")

        # --- Step 1b: Visual deduplication pre-filter (optional) ---
        tokens_saved_by_visual_dedup = 0
        if not request.skip_visual_dedup:
            from app.services.dedup_service import get_dedup_service

            dedup_svc = get_dedup_service()
            if dedup_svc.effective_backend != "native":
                await _log(
                    job_id, "INFO",
                    f"[Paso 1b/5] Aplicando deduplicación visual ({dedup_svc.effective_backend}) "
                    f"sobre {len(unique_files)} archivo(s) únicos…",
                    db,
                )
                unique_files = await loop.run_in_executor(
                    None, dedup_svc.find_visual_duplicates, unique_files
                )
                tokens_saved_by_visual_dedup = sum(1 for f in unique_files if f.is_duplicate)
                if tokens_saved_by_visual_dedup:
                    await _log(
                        job_id, "INFO",
                        f"[Paso 1b/5] Deduplicación visual completada — "
                        f"{tokens_saved_by_visual_dedup} imagen(es) marcadas como duplicados visuales "
                        f"(ahorro estimado: {tokens_saved_by_visual_dedup} llamada(s) a Gemini).",
                        db,
                    )
                # Keep only visually unique files for Gemini
                unique_files = [f for f in unique_files if not f.is_duplicate]

        # --- Step 2: Gemini classification ---
        from app.services import gemini_service
        from app.services.document_extraction_service import (
            build_classification_context,
            extract_document_content,
        )

        await _log(job_id, "INFO", f"[Paso 2/5] Clasificando {len(unique_files)} archivo(s) con Gemini…", db)
        documents: list[DocumentMetadata] = []
        chunks: list[DocumentChunk] = []
        non_binary_files = 0  # files attempted for processing (excluding binary-detected files)

        for idx, fi in enumerate(unique_files):
            await _update_job(
                db, job_id,
                message=f"Clasificando ({idx + 1}/{len(unique_files)}): {fi.name}",
                extra_update={"processed_files": idx + 1},
            )
            await _log(job_id, "DEBUG", f"Clasificando [{idx + 1}/{len(unique_files)}]: {fi.path}", db)

            extraction = await loop.run_in_executor(None, extract_document_content, fi)
            await _log(
                job_id,
                "DEBUG",
                f"  → extracción={extraction.extraction_method}, partes={len(extraction.chunks)}",
                db,
            )

            if not extraction.text and not extraction.chunks:
                reason = f"({extraction.extraction_method})" if extraction.extraction_method not in ("none", "skipped_binary") else ""
                if extraction.extraction_method == "skipped_binary":
                    await _log(
                        job_id,
                        "DEBUG",
                        f"[Paso 2/5] Archivo binario detectado, saltando: {fi.path}",
                        db,
                    )
                else:
                    non_binary_files += 1  # non-binary but no text — still counts as attempted
                    await _log(
                        job_id,
                        "INFO",
                        f"[Paso 2/5] Archivo sin texto extraído {reason}, omitiendo clasificación/embedding: {fi.path}",
                        db,
                    )
                continue

            non_binary_files += 1

            classification_context = build_classification_context(extraction)
            if classification_context:
                await _log(
                    job_id,
                    "DEBUG",
                    f"  → contexto LLM={len(classification_context)} caracteres",
                    db,
                )

            doc = await loop.run_in_executor(
                None,
                gemini_service.classify_document,
                fi,
                classification_context or extraction.text,
            )
            await _log(job_id, "DEBUG",
                 f"  → categoría={doc.categoria}, pii={doc.pii_info.detected}", db)
            chunks.extend(extraction.chunks)

            # --- Step 3: Embeddings ---
            if request.enable_embeddings:
                from app.services import embeddings_service
                from app.db import vector_store

                embed_text = _build_embedding_text(doc, extraction.text)
                if embed_text:
                    await _log(
                        job_id,
                        "INFO",
                        f"[Paso 3/5] Embedding documento {doc.documento_id} "
                        f"path={fi.path} chars={len(embed_text)} model={settings.gemini_embedding_model}",
                        db,
                    )
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
                    await _log(
                        job_id,
                        "DEBUG",
                        f"[Paso 3/5] Embedding chunk {chunk.chunk_index} "
                        f"documento={doc.documento_id} path={chunk.source_path} "
                        f"chars={len(chunk_text)}",
                        db,
                    )
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

        # Bulk insert documents and chunks into DB
        for doc in documents:
            db.add(db_models.Document(
                documento_id=doc.documento_id,
                job_id=job_id,
                data=doc.model_dump(exclude={"embedding"}),
            ))
        for chunk in chunks:
            db.add(db_models.Chunk(
                chunk_id=chunk.chunk_id,
                job_id=job_id,
                documento_id=chunk.documento_id,
                data=chunk.model_dump(exclude={"embedding"}),
            ))
        await db.commit()

        # Correct total_files to reflect only the documents actually processed
        # (binary files and unextractable files are skipped, so they don't count).
        await _update_job(db, job_id, extra_update={"total_files": non_binary_files, "processed_files": non_binary_files})

        await _log(job_id, "INFO",
             f"[Paso 2/5] Clasificación completada — {len(documents)} documento(s) procesados", db)

        # --- Step 4: Clustering ---
        clusters = []
        if request.enable_clustering and documents:
            await _update_job(db, job_id, message="Construyendo clusters semánticos…")
            await _log(job_id, "INFO", "[Paso 3/5] Construyendo clusters semánticos…", db)
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
                await _log(job_id, "DEBUG", f"  → {len(chroma_data)} embeddings recuperados de ChromaDB", db)

            clusters = await loop.run_in_executor(
                None, build_clusters, documents, chroma_data
            )
            clusters = await loop.run_in_executor(
                None, detect_inconsistencies, clusters, documents
            )
            await _log(job_id, "INFO", f"[Paso 3/5] Clustering completado — {len(clusters)} cluster(s)", db)
        else:
            await _log(job_id, "INFO", "[Paso 3/5] Clustering omitido (deshabilitado o sin documentos)", db)

        # --- Step 5: Build health report ---
        await _update_job(db, job_id, message="Generando reporte de salud de datos…")
        await _log(job_id, "INFO", "[Paso 4/6] Generando reporte de salud de datos…", db)
        report = _build_report(job_id, file_indices, documents, clusters, tokens_saved_by_visual_dedup)
        db.add(db_models.Report(job_id=job_id, data=report.model_dump()))
        await db.commit()

        # --- Step 6: Group analysis ---
        if documents:
            await _update_job(db, job_id, message="Analizando grupos de directorio…")
            await _log(job_id, "INFO", "[Paso 5/6] Analizando grupos de directorio…", db)
            from app.services.grouping_service import analyze_all_groups

            group_analysis = await loop.run_in_executor(
                None,
                analyze_all_groups,
                job_id,
                documents,
                request.group_mode,
                10,
            )
            await store_group_analysis(db, job_id, group_analysis)
            await _log(job_id, "INFO", f"[Paso 5/6] Group analysis completado — {group_analysis.group_count} grupos", db)
        else:
            await _log(job_id, "INFO", "[Paso 5/6] No hay documentos para análisis de grupos", db)

        job_after = await _load_job_progress(db, job_id)
        total_files = (job_after.total_files if job_after else None) or len(file_indices)

        await _update_job(db, job_id, status=JobStatus.COMPLETED.value, message="Análisis completado.")
        await _log(job_id, "INFO", f"[Paso 6/6] Job {job_id} completado exitosamente ✓", db)
        await audit_log.record_async(
            db,
            "job.completed",
            resource_id=job_id,
            resource_type="job",
            path=request.path,
            source_provider=request.source_provider.value,
            total_files=total_files,
        )

    except Exception as exc:  # noqa: BLE001
        await _log(job_id, "ERROR", f"Job {job_id} falló: {exc!r}", db)
        logger.exception("Job %s failed", job_id)
        await _update_job(
            db, job_id,
            status=JobStatus.FAILED.value,
            error_message=repr(exc),
            message="Error durante el análisis.",
        )
        await audit_log.record_async(
            db,
            "job.failed",
            resource_id=job_id,
            resource_type="job",
            outcome="failure",
            error=repr(exc),
        )
    finally:
        if temp_scan_root:
            cleanup_source_path(temp_scan_root)


def _build_report(
    job_id: str,
    file_indices: list[Any],
    documents: list[DocumentMetadata],
    clusters: list[Any],
    tokens_saved_by_visual_dedup: int = 0,
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
        tokens_saved_by_visual_dedup=tokens_saved_by_visual_dedup,
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
