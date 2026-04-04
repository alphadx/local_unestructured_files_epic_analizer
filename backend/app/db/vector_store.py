from __future__ import annotations

"""
ChromaDB vector-store adapter.

Documents are stored as:
  - id        : documento_id (SHA-256 or path)
  - embedding : 768-dim float vector from Gemini text-embedding-004
  - metadata  : flat dict with categoria, cluster_sugerido, path, …
  - document  : resumen text used for nearest-neighbour search

ChromaDB is an optional dependency.  All public functions degrade gracefully
when the library is not installed or the server is unreachable.
"""

import logging

from app.config import settings
from app.models.schemas import DocumentMetadata

logger = logging.getLogger(__name__)

_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is not None:
        return _collection

    try:
        import chromadb  # type: ignore
        from chromadb.config import Settings as ChromaSettings  # type: ignore

        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Connected to ChromaDB at %s:%d", settings.chroma_host, settings.chroma_port
        )
    except ImportError:
        logger.warning("chromadb not installed – vector store disabled")
        _collection = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("ChromaDB unavailable – vector store disabled: %s", exc)
        _collection = None
    return _collection


def upsert_document(doc: DocumentMetadata) -> None:
    """Insert or update a document's embedding in ChromaDB."""
    if doc.embedding is None:
        return
    col = _get_collection()
    if col is None:
        return

    meta = {
        "categoria": doc.categoria.value,
        "cluster_sugerido": doc.analisis_semantico.cluster_sugerido or "",
        "path": doc.file_index.path,
        "risk_level": doc.pii_info.risk_level.value,
        "confianza": doc.analisis_semantico.confianza_clasificacion or 0.0,
    }
    try:
        col.upsert(
            ids=[doc.documento_id],
            embeddings=[doc.embedding],
            metadatas=[meta],
            documents=[doc.analisis_semantico.resumen or ""],
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("ChromaDB upsert failed: %s", exc)


def query_similar(embedding: list[float], n_results: int = 10) -> list[dict]:
    """Return the n closest documents to the given embedding."""
    col = _get_collection()
    if col is None:
        return []
    try:
        results = col.query(query_embeddings=[embedding], n_results=n_results)
        items = []
        for i, doc_id in enumerate(results["ids"][0]):
            items.append(
                {
                    "id": doc_id,
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "document": results["documents"][0][i],
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.error("ChromaDB query failed: %s", exc)
        return []


def get_all_embeddings() -> list[dict]:
    """Return all stored documents with their embeddings (for local clustering)."""
    col = _get_collection()
    if col is None:
        return []
    try:
        result = col.get(include=["embeddings", "metadatas", "documents"])
        items = []
        for i, doc_id in enumerate(result["ids"]):
            items.append(
                {
                    "id": doc_id,
                    "embedding": result["embeddings"][i],
                    "metadata": result["metadatas"][i],
                    "document": result["documents"][i],
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001
        logger.error("ChromaDB get_all failed: %s", exc)
        return []


def reset_collection() -> None:
    """Drop and recreate the collection (useful for a fresh scan)."""
    global _collection
    col = _get_collection()
    if col is None:
        return
    try:
        _client.delete_collection(settings.chroma_collection)
        _collection = None
        _get_collection()
    except Exception as exc:  # noqa: BLE001
        logger.error("ChromaDB reset failed: %s", exc)
