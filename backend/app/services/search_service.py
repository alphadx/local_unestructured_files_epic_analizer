from __future__ import annotations

from collections import Counter
import re
from pathlib import Path

from app.db import vector_store
from app.models.schemas import (
    DocumentChunk,
    DocumentMetadata,
    SearchFacet,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchScope,
)
from app.services import embeddings_service
from app.services.analytics_service import normalize_directory, normalize_extension
from app.services import job_manager

_MAX_SNIPPET_CHARS = 240


def _share(count: int, total: int) -> float:
    return count / total if total else 0.0


def _matches_filters(
    doc: DocumentMetadata | DocumentChunk,
    *,
    categories: set[str],
    extensions: set[str],
    directories: set[str],
    doc_by_id: dict[str, DocumentMetadata] | None = None,
) -> bool:
    if categories:
        category_value: str | None = None
        if isinstance(doc, DocumentMetadata):
            category_value = doc.categoria.value
        elif doc_by_id is not None:
            parent = doc_by_id.get(doc.documento_id)
            category_value = parent.categoria.value if parent else None
        if category_value is None:
            return False
        if category_value not in categories:
            return False

    if extensions:
        extension = (
            normalize_extension(doc.file_index.extension)
            if isinstance(doc, DocumentMetadata)
            else normalize_extension(Path(doc.source_path).suffix)
        )
        if extension not in extensions:
            return False

    if directories:
        path = doc.file_index.path if isinstance(doc, DocumentMetadata) else doc.source_path
        if normalize_directory(path) not in directories:
            return False

    return True


def _document_snippet(doc: DocumentMetadata) -> str:
    parts = [
        doc.analisis_semantico.resumen,
        " ".join(doc.analisis_semantico.palabras_clave),
        doc.file_index.name,
        doc.file_index.path,
    ]
    text = " ".join(part for part in parts if part).strip()
    return re.sub(r"\s+", " ", text)[:_MAX_SNIPPET_CHARS]


def _chunk_snippet(chunk: DocumentChunk) -> str:
    return re.sub(r"\s+", " ", chunk.text).strip()[:_MAX_SNIPPET_CHARS]


def _keyword_matches(
    query: str | None,
    doc: DocumentMetadata | DocumentChunk,
) -> bool:
    if not query:
        return True
    haystacks: list[str] = []
    if isinstance(doc, DocumentMetadata):
        haystacks = [
            doc.file_index.name,
            doc.file_index.path,
            doc.categoria.value,
            doc.analisis_semantico.resumen or "",
            " ".join(doc.analisis_semantico.palabras_clave),
        ]
    else:
        haystacks = [doc.text, doc.title or "", doc.source_path]
    combined = " ".join(haystacks).lower()
    return all(term in combined for term in query.lower().split())


def _result_from_document(doc: DocumentMetadata) -> SearchResult:
    return SearchResult(
        source_id=f"doc::{doc.documento_id}",
        kind="document",
        title=doc.file_index.name,
        path=doc.file_index.path,
        document_id=doc.documento_id,
        category=doc.categoria.value,
        cluster_sugerido=doc.analisis_semantico.cluster_sugerido,
        snippet=_document_snippet(doc),
        score=doc.analisis_semantico.confianza_clasificacion or 0.0,
        distance=max(0.0, 1.0 - (doc.analisis_semantico.confianza_clasificacion or 0.0)),
    )


def _result_from_chunk(
    chunk: DocumentChunk,
    doc_by_id: dict[str, DocumentMetadata],
    *,
    score: float = 0.0,
    distance: float = 1.0,
) -> SearchResult:
    doc = doc_by_id.get(chunk.documento_id)
    return SearchResult(
        source_id=f"chunk::{chunk.chunk_id}",
        kind="chunk",
        title=chunk.title,
        path=chunk.source_path,
        document_id=chunk.documento_id,
        category=doc.categoria.value if doc else "Desconocido",
        cluster_sugerido=doc.analisis_semantico.cluster_sugerido if doc else None,
        snippet=_chunk_snippet(chunk),
        score=score,
        distance=distance,
    )


def search_corpus(request: SearchRequest) -> SearchResponse:
    if request.job_id:
        documents = job_manager.get_documents(request.job_id)
        chunks = job_manager.get_chunks(request.job_id)
    else:
        documents = [doc for job in job_manager.list_jobs() for doc in job_manager.get_documents(job.job_id)]
        chunks = [chunk for job in job_manager.list_jobs() for chunk in job_manager.get_chunks(job.job_id)]

    if request.job_id and not documents:
        return SearchResponse(query=request.query, job_id=request.job_id, total_results=0)

    docs_by_id = {doc.documento_id: doc for doc in documents}

    categories = {item for item in request.category if item}
    extensions = {normalize_extension(item) for item in request.extension if item}
    directories = {normalize_directory(item) for item in request.directory if item}

    results: list[SearchResult] = []
    seen_ids: set[str] = set()

    semantic_hits: list[dict] = []
    if request.query:
        embedding = embeddings_service.embed_text(request.query)
        if embedding is not None:
            semantic_hits = vector_store.query_similar(
                embedding,
                n_results=max(20, request.top_k * 3),
                where={"job_id": request.job_id} if request.job_id else None,
            )

    if request.scope in {SearchScope.ALL, SearchScope.DOCUMENTS, SearchScope.HYBRID}:
        for doc in documents:
            if not _matches_filters(
                doc,
                categories=categories,
                extensions=extensions,
                directories=directories,
                doc_by_id=docs_by_id,
            ):
                continue
            if not _keyword_matches(request.query, doc):
                continue
            result = _result_from_document(doc)
            if request.query:
                result.score = max(result.score, 0.35)
                result.distance = max(0.0, 1.0 - result.score)
            if result.source_id not in seen_ids:
                seen_ids.add(result.source_id)
                results.append(result)

    if request.scope in {SearchScope.ALL, SearchScope.CHUNKS, SearchScope.HYBRID}:
        for chunk in chunks:
            if not _matches_filters(
                chunk,
                categories=categories,
                extensions=extensions,
                directories=directories,
                doc_by_id=docs_by_id,
            ):
                continue
            if not _keyword_matches(request.query, chunk):
                continue
            result = _result_from_chunk(chunk, docs_by_id)
            if result.source_id not in seen_ids:
                seen_ids.add(result.source_id)
                results.append(result)

    for hit in semantic_hits:
        metadata = hit.get("metadata") or {}
        kind = str(metadata.get("kind") or "document")
        if kind == "chunk":
            source_id = f"chunk::{hit['id'].removeprefix('chunk::')}"
            if source_id in seen_ids:
                continue
            chunk = next((item for item in chunks if f"chunk::{item.chunk_id}" == source_id), None)
            if chunk is None:
                continue
            if not _matches_filters(
                chunk,
                categories=categories,
                extensions=extensions,
                directories=directories,
                doc_by_id=docs_by_id,
            ):
                continue
            result = _result_from_chunk(
                chunk,
                docs_by_id,
                score=max(0.0, 1.0 - float(hit.get("distance", 0.0))),
                distance=float(hit.get("distance", 0.0)),
            )
        else:
            source_id = f"doc::{hit['id'].removeprefix('doc::')}"
            if source_id in seen_ids:
                continue
            doc = docs_by_id.get(metadata.get("document_id"))
            if doc is None:
                continue
            result = _result_from_document(doc)
            result.score = max(0.0, 1.0 - float(hit.get("distance", 0.0)))
            result.distance = float(hit.get("distance", 0.0))
        seen_ids.add(result.source_id)
        results.append(result)

    results = sorted(results, key=lambda item: item.score, reverse=True)[: request.top_k]

    total = len(results)
    categories_facets = [
        SearchFacet(label=label, count=count, share=_share(count, total))
        for label, count in Counter(result.category for result in results).most_common(5)
    ]
    extensions_facets = [
        SearchFacet(
            label=label,
            count=count,
            share=_share(count, total),
        )
        for label, count in Counter(
            normalize_extension(Path(result.path).suffix)
            for result in results
        ).most_common(5)
    ]
    directories_facets = [
        SearchFacet(label=label, count=count, share=_share(count, total))
        for label, count in Counter(normalize_directory(result.path) for result in results).most_common(5)
    ]

    suggestions = [
        "Filtra por categoría para reducir ruido semántico.",
        "Usa /exploration para identificar directorios dominantes antes de buscar.",
        "Combina query semántica con directory o category para acotar resultados.",
    ]
    if request.query:
        suggestions.insert(0, f"Búsqueda ejecutada para: {request.query}")

    return SearchResponse(
        query=request.query,
        job_id=request.job_id,
        total_results=len(results),
        results=results,
        categories=categories_facets,
        extensions=extensions_facets,
        directories=directories_facets,
        suggestions=suggestions,
    )
