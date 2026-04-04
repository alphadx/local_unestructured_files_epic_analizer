"""
Tests for the document extraction service.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.document_extraction_service import extract_document_content


def test_extracts_text_file_into_chunks(tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("# Title\n\nPrimer párrafo.\n\nSegundo párrafo.", encoding="utf-8")

    from app.models.schemas import FileIndex

    file_index = FileIndex(
        path=str(doc),
        name=doc.name,
        extension=".md",
        size_bytes=doc.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="abc123",
        mime_type="text/markdown",
    )

    result = extract_document_content(file_index)

    assert result.documento_id == "abc123"
    assert result.source_path == str(doc)
    assert result.text
    assert result.extraction_method in {"text-file", "unstructured"}
    assert len(result.chunks) >= 1
    assert all(chunk.documento_id == "abc123" for chunk in result.chunks)
    assert all(chunk.text for chunk in result.chunks)
