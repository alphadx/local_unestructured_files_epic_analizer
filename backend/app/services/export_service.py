from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.models.schemas import DocumentMetadata


def documents_to_json_payload(documents: list[DocumentMetadata]) -> list[dict[str, Any]]:
    """Serialize documents to a JSON-friendly payload."""
    return jsonable_encoder(documents)


def documents_to_csv(documents: list[DocumentMetadata]) -> str:
    """Export documents as flat CSV rows suitable for audits and BI tools."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "documento_id",
            "path",
            "name",
            "extension",
            "size_bytes",
            "mime_type",
            "sha256",
            "is_duplicate",
            "duplicate_of",
            "categoria",
            "emisor",
            "receptor",
            "monto_total",
            "moneda",
            "id_licitacion_vinculada",
            "id_ot_referencia",
            "resumen",
            "cluster_sugerido",
            "confianza_clasificacion",
            "palabras_clave",
            "pii_detected",
            "pii_risk_level",
            "pii_details",
            "fecha_emision",
            "periodo_fiscal",
            "created_at",
            "modified_at",
        ],
    )
    writer.writeheader()

    for doc in documents:
        writer.writerow(
            {
                "documento_id": doc.documento_id,
                "path": doc.file_index.path,
                "name": doc.file_index.name,
                "extension": doc.file_index.extension,
                "size_bytes": doc.file_index.size_bytes,
                "mime_type": doc.file_index.mime_type or "",
                "sha256": doc.file_index.sha256,
                "is_duplicate": doc.file_index.is_duplicate,
                "duplicate_of": doc.file_index.duplicate_of or "",
                "categoria": doc.categoria.value,
                "emisor": doc.entidades.emisor or "",
                "receptor": doc.entidades.receptor or "",
                "monto_total": doc.entidades.monto_total,
                "moneda": doc.entidades.moneda or "",
                "id_licitacion_vinculada": doc.relaciones.id_licitacion_vinculada or "",
                "id_ot_referencia": doc.relaciones.id_ot_referencia or "",
                "resumen": doc.analisis_semantico.resumen or "",
                "cluster_sugerido": doc.analisis_semantico.cluster_sugerido or "",
                "confianza_clasificacion": doc.analisis_semantico.confianza_clasificacion,
                "palabras_clave": "; ".join(doc.analisis_semantico.palabras_clave),
                "pii_detected": doc.pii_info.detected,
                "pii_risk_level": doc.pii_info.risk_level.value,
                "pii_details": "; ".join(doc.pii_info.details),
                "fecha_emision": doc.fecha_emision or "",
                "periodo_fiscal": doc.periodo_fiscal or "",
                "created_at": doc.file_index.created_at,
                "modified_at": doc.file_index.modified_at,
            }
        )

    return output.getvalue()
