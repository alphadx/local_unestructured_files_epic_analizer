from __future__ import annotations

from collections import Counter

from app.models.schemas import DataHealthReport, DocumentMetadata
from app.services import gemini_service


def _build_draft_summary(
    job_id: str,
    report: DataHealthReport,
    documents: list[DocumentMetadata],
) -> str:
    total_docs = len(documents)
    pii_share = (report.pii_files / total_docs) if total_docs else 0.0
    duplicate_share = (report.duplicates / report.total_files) if report.total_files else 0.0

    category_counts = Counter(doc.categoria.value for doc in documents)
    top_categories = ", ".join(
        f"{name} ({count})" for name, count in category_counts.most_common(3)
    ) or "Sin categorias dominantes"

    top_clusters = ", ".join(
        f"{cluster.label} ({cluster.document_count})"
        for cluster in sorted(
            report.clusters,
            key=lambda c: c.document_count,
            reverse=True,
        )[:3]
    ) or "Sin clusters"

    inconsistencies = len(report.consistency_errors)
    risk_level = "alto" if pii_share > 0.15 else "medio" if pii_share > 0.05 else "bajo"

    lines = [
        f"Resumen Ejecutivo - Job {job_id}",
        "",
        "1. Estado general",
        f"- Archivos indexados: {report.total_files}",
        f"- Documentos clasificados: {total_docs}",
        f"- Duplicados detectados: {report.duplicates} ({duplicate_share:.1%})",
        f"- Archivos con PII: {report.pii_files} ({pii_share:.1%})",
        f"- Nivel de riesgo inferido: {risk_level}",
        "",
        "2. Composicion documental",
        f"- Categorias dominantes: {top_categories}",
        f"- Clusters dominantes: {top_clusters}",
        "",
        "3. Calidad y consistencia",
        f"- Inconsistencias detectadas: {inconsistencies}",
        f"- Archivos sin categorizar: {report.uncategorised_files}",
        "",
        "4. Recomendaciones",
        "- Revisar duplicados para consolidacion documental.",
        "- Priorizar remediacion de PII en riesgo amarillo/rojo.",
        "- Validar inconsistencias de relaciones antes de reorganizar.",
    ]
    return "\n".join(lines)


def _enhance_with_gemini(draft: str, use_gemini: bool) -> str:
    if not use_gemini:
        return draft

    if not gemini_service.settings.gemini_api_key:
        return draft

    try:
        client = gemini_service._get_client()
        prompt = (
            "Mejora este resumen ejecutivo para auditoria documental en espanol. "
            "Conserva hechos y numeros, no inventes datos. "
            "Devuelve texto plano con secciones numeradas breves.\n\n"
            f"{draft}"
        )
        response = client.models.generate_content(
            model=gemini_service.settings.gemini_flash_model,
            contents=prompt,
        )
        text = (response.text or "").strip()
        return text or draft
    except Exception:
        return draft


def build_executive_summary_text(
    job_id: str,
    report: DataHealthReport,
    documents: list[DocumentMetadata],
    *,
    use_gemini: bool = True,
) -> str:
    draft = _build_draft_summary(job_id, report, documents)
    return _enhance_with_gemini(draft, use_gemini=use_gemini)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_to_pdf_lines(text: str, max_chars: int = 95) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        while len(line) > max_chars:
            lines.append(line[:max_chars])
            line = line[max_chars:]
        lines.append(line)
    return lines


def render_summary_pdf(text: str) -> bytes:
    """Render plain text into a minimal multi-page PDF."""
    lines = _text_to_pdf_lines(text)
    if not lines:
        lines = ["Resumen ejecutivo vacio"]

    lines_per_page = 44
    pages: list[list[str]] = [
        lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)
    ]

    objects: dict[int, bytes] = {}
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    page_object_numbers: list[int] = []
    next_obj = 4
    for page_lines in pages:
        page_obj = next_obj
        content_obj = next_obj + 1
        next_obj += 2

        page_object_numbers.append(page_obj)

        stream_lines = [b"BT", b"/F1 11 Tf", b"50 760 Td", b"14 TL"]
        for ln in page_lines:
            escaped = _pdf_escape(ln)
            stream_lines.append(f"({escaped}) Tj".encode("ascii", "ignore"))
            stream_lines.append(b"T*")
        stream_lines.append(b"ET")
        stream = b"\n".join(stream_lines) + b"\n"

        objects[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"endstream"
        )
        objects[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode("ascii")

    kids = " ".join(f"{obj_id} 0 R" for obj_id in page_object_numbers)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode(
        "ascii"
    )
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    ordered_ids = sorted(objects.keys())
    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets: dict[int, int] = {}

    for obj_id in ordered_ids:
        offsets[obj_id] = len(body)
        body.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        body.extend(objects[obj_id])
        body.extend(b"\nendobj\n")

    xref_offset = len(body)
    max_obj = max(ordered_ids)
    body.extend(f"xref\n0 {max_obj + 1}\n".encode("ascii"))
    body.extend(b"0000000000 65535 f \n")
    for obj_id in range(1, max_obj + 1):
        offset = offsets.get(obj_id, 0)
        body.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    body.extend(
        (
            "trailer\n"
            f"<< /Size {max_obj + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )

    return bytes(body)
