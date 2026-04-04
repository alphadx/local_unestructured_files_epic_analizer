from __future__ import annotations

"""
Vector-store adapter.

The adapter is intentionally configurable so the same code can target:

- a local ChromaDB container for development
- a remote ChromaDB instance or cloud endpoint for production

The collection stores both logical documents and semantic chunks so retrieval
can support RAG and clustering with a single source of truth.
"""

import logging
from typing import Any

from app.config import settings
from app.models.schemas import DocumentChunk, DocumentMetadata

logger = logging.getLogger(__name__)

_client = None
_collection = None


def _is_chroma_provider() -> bool:
    return settings.vector_store_provider.strip().lower() in {"chroma", "chromadb"}


def _client_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": settings.chroma_host,
        "port": settings.chroma_port,
        "settings": None,
    }
    if settings.vector_store_ssl:
        kwargs["ssl"] = True
    if settings.vector_store_headers:
        kwargs["headers"] = settings.vector_store_headers
    return kwargs


def _connect_client():
    if not _is_chroma_provider():
        raise RuntimeError(
            f"Unsupported vector store provider: {settings.vector_store_provider!r}"
        )

    import chromadb  # type: ignore
    from chromadb.config import Settings as ChromaSettings  # type: ignore

    kwargs = _client_kwargs()
    kwargs["settings"] = ChromaSettings(anonymized_telemetry=False)
    return chromadb.HttpClient(**kwargs)


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    try:
        _client = _connect_client()
        _collection = _client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Connected to vector store provider=%s at %s:%d",
            settings.vector_store_provider,
            settings.chroma_host,
            settings.chroma_port,
        )
    except ImportError:
        logger.warning("chromadb not installed – vector store disabled")
        _collection = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector store unavailable – disabled: %s", exc)
        _collection = None
    return _collection


def _base_metadata(
    *,
    job_id: str | None,
    kind: str,
    path: str,
    document_id: str,
    category: str,
    cluster_sugerido: str,
    risk_level: str,
    confidence: float,
    title: str | None = None,
    chunk_index: int | None = None,
    page_number: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job_id or "",
        "kind": kind,
        "path": path,
        "document_id": document_id,
        "category": category,
        "cluster_sugerido": cluster_sugerido,
        "risk_level": risk_level,
        "confidence": confidence,
    }
    if title:
        payload["title"] = title
    if chunk_index is not None:
        payload["chunk_index"] = chunk_index
    if page_number is not None:
        payload["page_number"] = page_number
    return payload


def upsert_document(doc: DocumentMetadata, *, job_id: str | None = None) -> None:
    """Insert or update a document's embedding in the vector store."""
    if doc.embedding is None:
        return
    col = _get_collection()
    if col is None:
        return

    meta = _base_metadata(
        job_id=job_id,
        kind="document",
        path=doc.file_index.path,
        document_id=doc.documento_id,
        category=doc.categoria.value,
        cluster_sugerido=doc.analisis_semantico.cluster_sugerido or "",
        risk_level=doc.pii_info.risk_level.value,
        confidence=doc.analisis_semantico.confianza_clasificacion or 0.0,
    )
    try:
        col.upsert(
            ids=[f"doc::{doc.documento_id}"],
            embeddings=[doc.embedding],
            metadatas=[meta],
            documents=[doc.analisis_semantico.resumen or ""],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Vector store upsert for document failed: %s", exc)


def upsert_chunk(
    chunk: DocumentChunk,
    *,
    job_id: str | None = None,
    category: str = "",
    cluster_sugerido: str = "",
    risk_level: str = "",
    confidence: float = 0.0,
) -> None:
    if chunk.embedding is None:
        return
    col = _get_collection()
    if col is None:
        return

    meta = _base_metadata(
        job_id=job_id,
        kind="chunk",
        path=chunk.source_path,
        document_id=chunk.documento_id,
        category=category,
        cluster_sugerido=cluster_sugerido,
        risk_level=risk_level,
        confidence=confidence,
        title=chunk.title,
        chunk_index=chunk.chunk_index,
        page_number=chunk.page_number,
    )
    try:
        col.upsert(
            ids=[f"chunk::{chunk.chunk_id}"],
            embeddings=[chunk.embedding],
            metadatas=[meta],
            documents=[chunk.text],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Vector store upsert for chunk failed: %s", exc)


def query_similar(
    embedding: list[float],
    n_results: int = 10,
    where: dict[str, Any] | None = None,
) -> list[dict]:
    """Return the n closest records to the given embedding."""
    col = _get_collection()
    if col is None:
        return []
    try:
        results = col.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
        )
        items: list[dict] = []
        ids = results.get("ids", [[]])[0]
        for i, record_id in enumerate(ids):
            items.append(
                {
                    "id": record_id,
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "document": results["documents"][0][i],
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.error("Vector store query failed: %s", exc)
        return []


def get_all_embeddings(kind: str | None = None) -> list[dict]:
    """Return stored records with embeddings for analytics and clustering."""
    col = _get_collection()
    if col is None:
        return []
    try:
        include = ["embeddings", "metadatas", "documents"]
        result = col.get(include=include)
        items: list[dict] = []
        for i, record_id in enumerate(result["ids"]):
            metadata = result["metadatas"][i] or {}
            if kind and metadata.get("kind") != kind:
                continue
            items.append(
                {
                    "id": record_id,
                    "embedding": result["embeddings"][i],
                    "metadata": metadata,
                    "document": result["documents"][i],
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.error("Vector store get_all failed: %s", exc)
        return []


def reset_collection() -> None:
    """Drop and recreate the collection when allowed by configuration."""
    global _collection
    if not settings.vector_store_allow_reset:
        logger.warning("Vector store reset disabled by configuration")
        return
    col = _get_collection()
    if col is None:
        return
    try:
        _client.delete_collection(settings.chroma_collection)
        _collection = None
        _get_collection()
    except Exception as exc:  # noqa: BLE001
        logger.error("Vector store reset failed: %s", exc)
