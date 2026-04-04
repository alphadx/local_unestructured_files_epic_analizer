"""
Tests for the vector store adapter.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.db import vector_store
from app.models.schemas import (
    DocumentChunk,
    DocumentCategory,
    DocumentEntities,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    PiiInfo,
    RiskLevel,
    SemanticAnalysis,
)


class _FakeCollection:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.queries: list[dict] = []
        self.records = {
            "ids": [["doc::1", "chunk::1"]],
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            "metadatas": [[
                {"kind": "document", "job_id": "job-1"},
                {"kind": "chunk", "job_id": "job-1"},
            ]],
            "documents": [["Resumen", "Fragmento"]],
            "distances": [[0.1, 0.2]],
        }

    def upsert(self, **kwargs):  # noqa: ANN003
        self.upserts.append(kwargs)

    def query(self, **kwargs):  # noqa: ANN003
        self.queries.append(kwargs)
        return self.records

    def get(self, **kwargs):  # noqa: ANN003
        return self.records


def _document() -> DocumentMetadata:
    file_index = FileIndex(
        path="/data/doc.pdf",
        name="doc.pdf",
        extension=".pdf",
        size_bytes=123,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="abc",
        mime_type="application/pdf",
    )
    return DocumentMetadata(
        documento_id="abc",
        file_index=file_index,
        categoria=DocumentCategory.REPORT,
        entidades=DocumentEntities(),
        relaciones=DocumentRelations(),
        analisis_semantico=SemanticAnalysis(
            resumen="Resumen",
            cluster_sugerido="Informes",
            confianza_clasificacion=0.91,
            palabras_clave=["analisis"],
        ),
        pii_info=PiiInfo(detected=True, risk_level=RiskLevel.YELLOW),
        embedding=[0.1, 0.2],
    )


def test_upsert_document_uses_document_metadata(monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store, "_get_collection", lambda: fake)

    vector_store.upsert_document(_document(), job_id="job-1")

    assert len(fake.upserts) == 1
    payload = fake.upserts[0]
    assert payload["ids"] == ["doc::abc"]
    assert payload["metadatas"][0]["kind"] == "document"
    assert payload["metadatas"][0]["job_id"] == "job-1"


def test_upsert_chunk_uses_chunk_metadata(monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store, "_get_collection", lambda: fake)

    chunk = DocumentChunk(
        chunk_id="abc::chunk::0000",
        documento_id="abc",
        source_path="/data/doc.pdf",
        chunk_index=0,
        text="Fragmento",
        title="Intro",
        page_number=1,
        token_count=2,
        embedding=[0.3, 0.4],
    )
    vector_store.upsert_chunk(
        chunk,
        job_id="job-1",
        category="Informe",
        cluster_sugerido="Informes",
        risk_level="verde",
        confidence=0.88,
    )

    assert len(fake.upserts) == 1
    payload = fake.upserts[0]
    assert payload["ids"] == ["chunk::abc::chunk::0000"]
    assert payload["metadatas"][0]["kind"] == "chunk"
    assert payload["metadatas"][0]["chunk_index"] == 0
    assert payload["metadatas"][0]["job_id"] == "job-1"


def test_query_similar_applies_filter(monkeypatch):
    fake = _FakeCollection()
    monkeypatch.setattr(vector_store, "_get_collection", lambda: fake)

    results = vector_store.query_similar([0.1, 0.2], n_results=2, where={"job_id": "job-1"})

    assert fake.queries[0]["where"] == {"job_id": "job-1"}
    assert len(results) == 2
    assert results[0]["id"] == "doc::1"
