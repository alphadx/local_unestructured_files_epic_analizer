from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from pathlib import Path

from app.models.schemas import ArtifactKind, DocumentChunk, FileIndex

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".json", ".xml", ".html", ".htm"}
_MAX_CHUNK_CHARS = 1_200
_MAX_TEXT_CHARS = 20_000
_MAX_CLASSIFICATION_CHARS = 12_000


@dataclass(slots=True)
class DocumentExtraction:
    documento_id: str
    source_path: str
    text: str
    chunks: list[DocumentChunk]
    extraction_method: str
    element_count: int = 0


def _read_text_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read(_MAX_TEXT_CHARS)


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _chunk_text(
    documento_id: str,
    source_path: str,
    text: str,
    *,
    title: str | None = None,
    section_path: list[str] | None = None,
    page_number: int | None = None,
) -> list[DocumentChunk]:
    cleaned = _normalize_text(text)
    if not cleaned:
        return []

    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [cleaned]

    chunks: list[DocumentChunk] = []
    buffer = ""
    chunk_index = 0

    def _emit(current_text: str) -> None:
        nonlocal chunk_index
        normalized = _normalize_text(current_text)
        if not normalized:
            return
        chunks.append(
            DocumentChunk(
                chunk_id=f"{documento_id}::chunk::{chunk_index:04d}",
                documento_id=documento_id,
                artifact_kind=ArtifactKind.CHUNK,
                source_path=source_path,
                chunk_index=chunk_index,
                text=normalized,
                title=title,
                section_path=list(section_path or []),
                page_number=page_number,
                token_count=max(1, len(normalized.split())),
            )
        )
        chunk_index += 1

    for paragraph in paragraphs:
        if len(paragraph) <= _MAX_CHUNK_CHARS:
            candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            if len(candidate) <= _MAX_CHUNK_CHARS:
                buffer = candidate
                continue
            _emit(buffer)
            buffer = paragraph
            continue

        if buffer:
            _emit(buffer)
            buffer = ""

        start = 0
        while start < len(paragraph):
            _emit(paragraph[start : start + _MAX_CHUNK_CHARS])
            start += _MAX_CHUNK_CHARS

    if buffer:
        _emit(buffer)

    return chunks


def _extract_with_unstructured(path: Path, documento_id: str) -> tuple[str, list[DocumentChunk], int]:
    try:
        from unstructured.partition.auto import partition  # type: ignore
    except ImportError:
        return "", [], 0

    try:
        elements = partition(filename=str(path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("unstructured partition failed for %s: %s", path, exc)
        return "", [], 0

    raw_parts: list[str] = []
    chunks: list[DocumentChunk] = []

    for idx, element in enumerate(elements):
        text = getattr(element, "text", "") or ""
        cleaned = _normalize_text(text)
        if not cleaned:
            continue
        raw_parts.append(cleaned)

        metadata = getattr(element, "metadata", None)
        title = getattr(element, "category", None) or element.__class__.__name__
        page_number = getattr(metadata, "page_number", None) if metadata else None
        section_path = []
        if title:
            section_path.append(str(title))
        chunks.extend(
            _chunk_text(
                documento_id=documento_id,
                source_path=str(path),
                text=cleaned,
                title=str(title) if title else None,
                section_path=section_path,
                page_number=page_number,
            )
        )

    return "\n\n".join(raw_parts), chunks, len(raw_parts)


def extract_document_content(file_index: FileIndex) -> DocumentExtraction:
    """
    Extract readable content and semantic chunks from a file.

    Uses `unstructured` when available and falls back to basic text extraction
    for plain-text documents. Binary formats degrade gracefully to an empty
    extraction so the rest of the pipeline can continue.
    """
    path = Path(file_index.path)
    documento_id = file_index.sha256 or file_index.path

    text = ""
    chunks: list[DocumentChunk] = []
    extraction_method = "none"
    element_count = 0

    if file_index.extension in _TEXT_EXTENSIONS or (
        file_index.mime_type and file_index.mime_type.startswith("text/")
    ):
        try:
            text = _read_text_file(path)
            extraction_method = "text-file"
        except OSError as exc:
            logger.warning("Unable to read text file %s: %s", path, exc)
            text = ""
        if text:
            chunks = _chunk_text(
                documento_id=documento_id,
                source_path=str(path),
                text=text,
                title=path.name,
                section_path=[path.parent.as_posix()],
            )
            element_count = len(chunks)

    if not chunks:
        unstructured_text, unstructured_chunks, count = _extract_with_unstructured(path, documento_id)
        if unstructured_chunks:
            text = unstructured_text
            chunks = unstructured_chunks
            extraction_method = "unstructured"
            element_count = count

    if not chunks and text:
        chunks = _chunk_text(
            documento_id=documento_id,
            source_path=str(path),
            text=text,
            title=path.name,
            section_path=[path.parent.as_posix()],
        )
        element_count = len(chunks)

    return DocumentExtraction(
        documento_id=documento_id,
        source_path=str(path),
        text=_normalize_text(text),
        chunks=chunks,
        extraction_method=extraction_method,
        element_count=element_count,
    )


def build_classification_context(extraction: DocumentExtraction) -> str:
    """
    Build a compact LLM input from extracted structure and text.

    The output keeps headings and chunk order while staying within a bounded
    character budget so the classifier sees the document shape, not just a raw
    blob of text.
    """
    lines: list[str] = []
    if extraction.extraction_method != "none":
        lines.append(f"Metodo de extraccion: {extraction.extraction_method}")

    if extraction.chunks:
        for chunk in extraction.chunks[:10]:
            label_parts = [f"chunk {chunk.chunk_index}"]
            if chunk.title:
                label_parts.append(chunk.title)
            if chunk.page_number is not None:
                label_parts.append(f"pagina {chunk.page_number}")
            heading = " | ".join(label_parts)
            body = _normalize_text(chunk.text)
            if len(body) > 2_000:
                body = body[:2_000].rstrip() + "..."
            lines.append(f"[{heading}]\n{body}")
    elif extraction.text:
        lines.append(extraction.text)

    context = "\n\n".join(lines).strip()
    return context[:_MAX_CLASSIFICATION_CHARS]
