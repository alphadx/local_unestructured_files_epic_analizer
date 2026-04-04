"""
Tests for the RAG service.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import (
    ArtifactKind,
    DocumentCategory,
    DocumentChunk,
    DocumentMetadata,
    FileIndex,
    RagQueryRequest,
)
from app.services import rag_service


def test_query_rag_builds_context_and_answer(monkeypatch):
    monkeypatch.setattr(rag_service.embeddings_service, "embed_text", lambda text: [0.1, 0.2])
    monkeypatch.setattr(
        rag_service.vector_store,
        "query_similar",
        lambda embedding, n_results=10, where=None: [
            {
                "id": "chunk::1",
                "distance": 0.2,
                "metadata": {
                    "kind": "chunk",
                    "document_id": "doc-1",
                    "path": "/data/doc.pdf",
                    "title": "Intro",
                    "category": "Informe",
                    "cluster_sugerido": "Informes",
                    "chunk_index": 0,
                    "page_number": 1,
                },
                "document": "Este es el fragmento principal.",
            }
        ],
    )
    monkeypatch.setattr(
        rag_service.gemini_service,
        "generate_rag_answer",
        lambda question, context: f"Respuesta: {question} | {context[:20]}",
    )

    response = rag_service.query_rag(
        RagQueryRequest(query="¿De qué trata este documento?", job_id="job-1", top_k=3)
    )

    assert response.query == "¿De qué trata este documento?"
    assert response.answer is not None
    assert "chunk::1" in response.context
    assert len(response.sources) == 1
    assert response.sources[0].source_id == "chunk::1"


def test_query_rag_falls_back_to_in_memory_chunks(monkeypatch):
    file_index = FileIndex(
        path="/data/doc.pdf",
        name="doc.pdf",
        extension=".pdf",
        size_bytes=123,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="abc123",
        mime_type="application/pdf",
    )
    document = DocumentMetadata(
        documento_id="doc-1",
        file_index=file_index,
        artifact_kind=ArtifactKind.LOGICAL_DOCUMENT,
        categoria=DocumentCategory.REPORT,
    )
    chunk = DocumentChunk(
        chunk_id="doc-1::chunk::0000",
        documento_id="doc-1",
        artifact_kind=ArtifactKind.CHUNK,
        source_path="/data/doc.pdf",
        chunk_index=0,
        text="Azure y Gemini se comparan en el documento.",
        title="Intro",
        section_path=["Intro"],
        page_number=1,
        token_count=8,
    )

    monkeypatch.setattr(rag_service.embeddings_service, "embed_text", lambda text: None)
    monkeypatch.setattr(rag_service.vector_store, "query_similar", lambda *args, **kwargs: [])
    monkeypatch.setattr(rag_service.job_manager, "get_documents", lambda job_id: [document])
    monkeypatch.setattr(rag_service.job_manager, "get_chunks", lambda job_id: [chunk])
    monkeypatch.setattr(
        rag_service.gemini_service,
        "generate_rag_answer",
        lambda question, context: f"Respuesta: {question} | {context[:20]}",
    )

    response = rag_service.query_rag(
        RagQueryRequest(query="¿Esto usa azure o gemini?", job_id="job-1", top_k=3)
    )

    assert response.answer is not None
    assert "Azure y Gemini" in response.context
    assert len(response.sources) == 2
    assert any(source.kind == "chunk" for source in response.sources)
