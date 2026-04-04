"""
Tests for the RAG service.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.models.schemas import RagQueryRequest
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
