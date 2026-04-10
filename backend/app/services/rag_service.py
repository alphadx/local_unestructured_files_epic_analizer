from __future__ import annotations

import inspect
import logging
import re
from dataclasses import dataclass

from app.db import vector_store
from app.models.schemas import RagQueryRequest, RagQueryResponse, RagSource
from app.services import job_manager
from app.services import embeddings_service, gemini_service

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 8_000
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(slots=True)
class _RagHit:
    source_id: str
    kind: str
    document_id: str | None
    path: str | None
    title: str | None
    category: str | None
    cluster_sugerido: str | None
    chunk_index: int | None
    page_number: int | None
    snippet: str
    distance: float
    score: float


def _score(distance: float) -> float:
    return max(0.0, min(1.0, 1.0 - distance))


def _build_where(job_id: str | None) -> dict[str, str] | None:
    if not job_id:
        return None
    return {"job_id": job_id}


def _normalize_hit(record: dict) -> _RagHit:
    metadata = record.get("metadata") or {}
    document = (record.get("document") or "").strip()
    return _RagHit(
        source_id=record["id"],
        kind=str(metadata.get("kind") or "unknown"),
        document_id=metadata.get("document_id"),
        path=metadata.get("path"),
        title=metadata.get("title"),
        category=metadata.get("category"),
        cluster_sugerido=metadata.get("cluster_sugerido"),
        chunk_index=metadata.get("chunk_index"),
        page_number=metadata.get("page_number"),
        snippet=document[:700],
        distance=float(record.get("distance", 0.0)),
        score=_score(float(record.get("distance", 0.0))),
    )


def _context_line(hit: _RagHit) -> str:
    parts = [f"[{hit.source_id}]"]
    if hit.kind:
        parts.append(hit.kind)
    if hit.category:
        parts.append(hit.category)
    if hit.path:
        parts.append(hit.path)
    if hit.title:
        parts.append(hit.title)
    if hit.chunk_index is not None:
        parts.append(f"chunk={hit.chunk_index}")
    if hit.page_number is not None:
        parts.append(f"page={hit.page_number}")
    header = " | ".join(parts)
    return f"{header}\n{hit.snippet}"


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.lower())
        if len(token) > 2
    }


def _lexical_score(query: str, haystack: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    haystack_tokens = _tokenize(haystack)
    if not haystack_tokens:
        return 0.0
    overlap = len(query_tokens & haystack_tokens)
    return overlap / len(query_tokens)


def _job_documents(job_id: str | None) -> list:
    if job_id:
        docs = job_manager.get_documents(job_id)
        if inspect.iscoroutine(docs):
            docs.close()
            return []
        if inspect.isawaitable(docs):
            return []
        return docs
    jobs = job_manager.list_jobs()
    if inspect.iscoroutine(jobs):
        jobs.close()
        return []
    if inspect.isawaitable(jobs):
        return []
    all_docs = []
    for job in jobs:
        docs = job_manager.get_documents(job.job_id)
        if inspect.iscoroutine(docs):
            docs.close()
            continue
        if inspect.isawaitable(docs):
            continue
        all_docs.extend(docs)
    return all_docs


def _job_chunks(job_id: str | None) -> list:
    if job_id:
        chunks = job_manager.get_chunks(job_id)
        if inspect.iscoroutine(chunks):
            chunks.close()
            return []
        if inspect.isawaitable(chunks):
            return []
        return chunks
    jobs = job_manager.list_jobs()
    if inspect.iscoroutine(jobs):
        jobs.close()
        return []
    if inspect.isawaitable(jobs):
        return []
    all_chunks = []
    for job in jobs:
        chunks = job_manager.get_chunks(job.job_id)
        if inspect.iscoroutine(chunks):
            chunks.close()
            continue
        if inspect.isawaitable(chunks):
            continue
        all_chunks.extend(chunks)
    return all_chunks


def _fallback_records(request: RagQueryRequest) -> list[dict]:
    documents = _job_documents(request.job_id)
    chunks = _job_chunks(request.job_id)
    doc_by_id = {doc.documento_id: doc for doc in documents}

    records: list[dict] = []
    for doc in documents:
        haystack = " ".join(
            part
            for part in [
                doc.file_index.name,
                doc.file_index.path,
                doc.categoria.value,
                doc.analisis_semantico.resumen or "",
                " ".join(doc.analisis_semantico.palabras_clave),
            ]
            if part
        )
        score = _lexical_score(request.query, haystack)
        records.append(
            {
                "id": f"doc::{doc.documento_id}",
                "distance": max(0.0, 1.0 - score),
                "metadata": {
                    "kind": "document",
                    "document_id": doc.documento_id,
                    "path": doc.file_index.path,
                    "title": doc.file_index.name,
                    "category": doc.categoria.value,
                    "cluster_sugerido": doc.analisis_semantico.cluster_sugerido,
                },
                "document": doc.analisis_semantico.resumen or doc.file_index.name,
            }
        )

    for chunk in chunks:
        doc = doc_by_id.get(chunk.documento_id)
        haystack = " ".join(
            part
            for part in [
                chunk.text,
                chunk.title or "",
                chunk.source_path,
                doc.analisis_semantico.resumen if doc else "",
                " ".join(doc.analisis_semantico.palabras_clave) if doc else "",
            ]
            if part
        )
        score = _lexical_score(request.query, haystack)
        records.append(
            {
                "id": f"chunk::{chunk.chunk_id}",
                "distance": max(0.0, 1.0 - score),
                "metadata": {
                    "kind": "chunk",
                    "document_id": chunk.documento_id,
                    "path": chunk.source_path,
                    "title": chunk.title,
                    "category": doc.categoria.value if doc else "Desconocido",
                    "cluster_sugerido": (
                        doc.analisis_semantico.cluster_sugerido if doc else None
                    ),
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                },
                "document": chunk.text,
            }
        )

    return sorted(
        records,
        key=lambda record: (
            -_score(float(record.get("distance", 0.0))),
            record["id"],
        ),
    )


def query_rag(request: RagQueryRequest) -> RagQueryResponse:
    embedding = embeddings_service.embed_text(request.query)
    records: list[dict] = []
    if embedding is not None:
        records = vector_store.query_similar(
            embedding,
            n_results=max(10, request.top_k * 2),
            where=_build_where(request.job_id),
        )

    if not records:
        records = _fallback_records(request)

    hits = [_normalize_hit(record) for record in records]

    unique_hits: list[_RagHit] = []
    seen_ids: set[str] = set()
    for hit in hits:
        if hit.source_id in seen_ids:
            continue
        seen_ids.add(hit.source_id)
        unique_hits.append(hit)
        if len(unique_hits) == request.top_k:
            break

    context_parts: list[str] = []
    current_len = 0
    for hit in unique_hits:
        block = _context_line(hit)
        if current_len + len(block) > _MAX_CONTEXT_CHARS:
            break
        context_parts.append(block)
        current_len += len(block)

    context = "\n\n".join(context_parts).strip()
    answer = (
        gemini_service.generate_rag_answer(request.query, context)
        if request.include_answer
        else None
    )

    return RagQueryResponse(
        query=request.query,
        answer=answer,
        context=context,
        sources=[
            RagSource(
                source_id=hit.source_id,
                kind=hit.kind,
                document_id=hit.document_id,
                path=hit.path,
                title=hit.title,
                category=hit.category,
                cluster_sugerido=hit.cluster_sugerido,
                chunk_index=hit.chunk_index,
                page_number=hit.page_number,
                snippet=hit.snippet,
                distance=hit.distance,
                score=hit.score,
            )
            for hit in unique_hits
        ],
    )
