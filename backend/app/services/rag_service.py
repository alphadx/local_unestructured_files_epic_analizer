from __future__ import annotations

import logging
from dataclasses import dataclass

from app.db import vector_store
from app.models.schemas import RagQueryRequest, RagQueryResponse, RagSource
from app.services import embeddings_service, gemini_service

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 8_000


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


def query_rag(request: RagQueryRequest) -> RagQueryResponse:
    embedding = embeddings_service.embed_text(request.query)
    if embedding is None:
        return RagQueryResponse(query=request.query, context="", sources=[])

    records = vector_store.query_similar(
        embedding,
        n_results=max(10, request.top_k * 2),
        where=_build_where(request.job_id),
    )
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
