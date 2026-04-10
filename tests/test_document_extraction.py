"""
Tests for the document extraction service.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

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


def test_prefers_unstructured_extraction_when_available(monkeypatch, tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("# Title\n\nPrimer párrafo.", encoding="utf-8")

    from app.models.schemas import ArtifactKind, DocumentChunk, FileIndex
    import app.services.document_extraction_service as extraction_service

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

    def fake_unstructured(path, documento_id):
        return (
            "# Title\n\nPrimer párrafo.",
            [
                DocumentChunk(
                    chunk_id="abc123::chunk::0000",
                    documento_id="abc123",
                    artifact_kind=ArtifactKind.CHUNK,
                    source_path=str(doc),
                    chunk_index=0,
                    text="Primer párrafo.",
                    title="Title",
                    section_path=["Title"],
                    page_number=None,
                    token_count=2,
                )
            ],
            1,
            None,
        )

    monkeypatch.setattr(extraction_service, "_extract_with_unstructured", fake_unstructured)

    result = extract_document_content(file_index)

    assert result.extraction_method == "unstructured"
    assert len(result.chunks) == 1
    assert result.text == "# Title\n\nPrimer párrafo."


def test_skips_binary_file_by_extension(tmp_path):
    """Test that binary files are skipped early based on extension."""
    from app.models.schemas import FileIndex

    # Create a fake executable file
    binary_file = tmp_path / "program.exe"
    binary_file.write_bytes(b"\x4d\x5a\x90\x00")  # MZ header for PE executable

    file_index = FileIndex(
        path=str(binary_file),
        name=binary_file.name,
        extension=".exe",
        size_bytes=binary_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="binary123",
        mime_type="application/x-msdownload",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method == "skipped_binary"
    assert result.text == ""
    assert len(result.chunks) == 0


def test_extracts_xlsx_with_openpyxl_fallback(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from app.models.schemas import FileIndex

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Datos"
    sheet["A1"] = "Nombre"
    sheet["B1"] = "Monto"
    sheet["A2"] = "Alice"
    sheet["B2"] = 1200
    xlsx_file = tmp_path / "dataset.xlsx"
    workbook.save(xlsx_file)
    workbook.close()

    file_index = FileIndex(
        path=str(xlsx_file),
        name=xlsx_file.name,
        extension=".xlsx",
        size_bytes=xlsx_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="xlsx123",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method == "openpyxl"
    assert len(result.chunks) >= 1
    assert "Alice" in result.text


def test_octet_stream_xlsx_is_not_skipped_as_binary(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    from app.models.schemas import FileIndex

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "Contenido"
    xlsx_file = tmp_path / "octet.xlsx"
    workbook.save(xlsx_file)
    workbook.close()

    file_index = FileIndex(
        path=str(xlsx_file),
        name=xlsx_file.name,
        extension=".xlsx",
        size_bytes=xlsx_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="octetxlsx",
        mime_type="application/octet-stream",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method != "skipped_binary"


def test_skips_binary_file_by_mime_type(tmp_path):
    """Test that binary files are skipped early based on MIME type."""
    from app.models.schemas import FileIndex

    # Create a fake image file
    image_file = tmp_path / "photo.jpg"
    image_file.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG header

    file_index = FileIndex(
        path=str(image_file),
        name=image_file.name,
        extension=".jpg",
        size_bytes=image_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="image123",
        mime_type="image/jpeg",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method == "skipped_binary"
    assert result.text == ""
    assert len(result.chunks) == 0


def test_skips_compressed_archive(tmp_path):
    """Test that compressed archives are skipped early."""
    from app.models.schemas import FileIndex

    # Create a fake ZIP file
    zip_file = tmp_path / "archive.zip"
    zip_file.write_bytes(b"PK\x03\x04")  # ZIP header

    file_index = FileIndex(
        path=str(zip_file),
        name=zip_file.name,
        extension=".zip",
        size_bytes=zip_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="zip123",
        mime_type="application/zip",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method == "skipped_binary"
    assert result.text == ""
    assert len(result.chunks) == 0


def test_extracts_docx_with_python_docx_fallback(tmp_path):
    docx = pytest.importorskip("docx")
    try:
        from app.models.schemas import FileIndex
    except ImportError:
        pytest.skip("Could not import schemas")

    doc = docx.Document()
    doc.add_paragraph("Primer párrafo de prueba docx.")
    doc.add_paragraph("Segundo párrafo con más contenido.")
    docx_file = tmp_path / "documento.docx"
    doc.save(docx_file)

    file_index = FileIndex(
        path=str(docx_file),
        name=docx_file.name,
        extension=".docx",
        size_bytes=docx_file.stat().st_size,
        created_at="2026-04-04T00:00:00",
        modified_at="2026-04-04T00:00:00",
        sha256="docx123",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    result = extract_document_content(file_index)

    assert result.extraction_method == "python-docx"
    assert len(result.chunks) >= 1
    assert "Primer párrafo" in result.text

