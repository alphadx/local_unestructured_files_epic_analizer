from __future__ import annotations

"""
Gemini service – document classification, PII detection, and metadata extraction.

Uses the google-genai SDK (google.genai).  When the API key is not configured
(development / testing) the service returns safe stub objects so that the rest
of the pipeline can still function.
"""

import json
import logging
from pathlib import Path

from app.config import settings
from app.models.schemas import (
    DocumentCategory,
    DocumentEntities,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    PiiInfo,
    RiskLevel,
    SemanticAnalysis,
)

logger = logging.getLogger(__name__)

_SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

_TEXT_EXTENSIONS = {".txt", ".csv", ".md", ".json", ".xml", ".html", ".htm"}

_CLASSIFICATION_PROMPT = """
Eres un experto contable y gestor de licitaciones chileno.
Analiza el siguiente documento y devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta:
{
  "categoria": "<Factura_Proveedor|Orden_Trabajo|Licitacion|Nota_Credito|Contrato|Informe|Imagen|Desconocido>",
  "entidades": {
    "emisor": "<nombre o RUT del emisor, null si no aplica>",
    "receptor": "<nombre o RUT del receptor, null si no aplica>",
    "monto_total": <número o null>,
    "moneda": "<CLP|USD|EUR|null>"
  },
  "relaciones": {
    "id_licitacion_vinculada": "<ID de licitación, null si no aplica>",
    "id_ot_referencia": "<ID de OT, null si no aplica>"
  },
  "analisis_semantico": {
    "resumen": "<párrafo de 2-3 líneas sobre qué trata el documento>",
    "cluster_sugerido": "<nombre descriptivo del cluster al que pertenece>",
    "confianza_clasificacion": <número entre 0 y 1>,
    "palabras_clave": ["<tag1>", "<tag2>", "<tag3>", "<tag4>", "<tag5>"]
  },
  "pii_info": {
    "detected": <true|false>,
    "risk_level": "<verde|amarillo|rojo>",
    "details": ["<descripción de PII encontrada>"]
  },
  "fecha_emision": "<YYYY-MM-DD o null>",
  "periodo_fiscal": "<YYYY-MM o null>"
}
No incluyas ningún texto fuera del JSON.
"""


def _get_client():
    """Return a configured google.genai Client."""
    from google import genai  # type: ignore

    return genai.Client(api_key=settings.gemini_api_key)


def _stub_metadata(file_index: FileIndex) -> DocumentMetadata:
    """Return a minimal metadata object when Gemini is not available."""
    return DocumentMetadata(
        documento_id=file_index.sha256 or file_index.path,
        file_index=file_index,
        categoria=DocumentCategory.UNKNOWN,
        analisis_semantico=SemanticAnalysis(
            resumen="[Gemini API not configured – stub metadata]",
            cluster_sugerido="Sin_Clasificar",
            confianza_clasificacion=0.0,
        ),
    )


def _parse_response(raw: str, file_index: FileIndex) -> DocumentMetadata:
    """Parse the JSON returned by Gemini into a DocumentMetadata object."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Gemini JSON response: %s", exc)
        return _stub_metadata(file_index)

    pii_raw = data.get("pii_info", {})
    sem_raw = data.get("analisis_semantico", {})

    try:
        categoria = DocumentCategory(data.get("categoria", DocumentCategory.UNKNOWN))
    except ValueError:
        categoria = DocumentCategory.UNKNOWN

    try:
        risk_level = RiskLevel(pii_raw.get("risk_level", RiskLevel.GREEN))
    except ValueError:
        risk_level = RiskLevel.GREEN

    return DocumentMetadata(
        documento_id=file_index.sha256 or file_index.path,
        file_index=file_index,
        categoria=categoria,
        entidades=DocumentEntities(
            emisor=data.get("entidades", {}).get("emisor"),
            receptor=data.get("entidades", {}).get("receptor"),
            monto_total=data.get("entidades", {}).get("monto_total"),
            moneda=data.get("entidades", {}).get("moneda"),
        ),
        relaciones=DocumentRelations(
            id_licitacion_vinculada=data.get("relaciones", {}).get("id_licitacion_vinculada"),
            id_ot_referencia=data.get("relaciones", {}).get("id_ot_referencia"),
        ),
        analisis_semantico=SemanticAnalysis(
            resumen=sem_raw.get("resumen"),
            cluster_sugerido=sem_raw.get("cluster_sugerido"),
            confianza_clasificacion=sem_raw.get("confianza_clasificacion"),
            palabras_clave=sem_raw.get("palabras_clave", []),
        ),
        pii_info=PiiInfo(
            detected=pii_raw.get("detected", False),
            risk_level=risk_level,
            details=pii_raw.get("details", []),
        ),
        fecha_emision=data.get("fecha_emision"),
        periodo_fiscal=data.get("periodo_fiscal"),
    )


def classify_document(file_index: FileIndex) -> DocumentMetadata:
    """
    Send a file to Gemini Flash for classification and metadata extraction.

    Falls back to a stub when the API key is absent or the call fails.
    """
    if not settings.gemini_api_key:
        logger.debug("Gemini API key not set – returning stub for %s", file_index.path)
        return _stub_metadata(file_index)

    from google import genai  # type: ignore
    from google.genai import types  # type: ignore

    client = _get_client()
    path = Path(file_index.path)

    try:
        mime = file_index.mime_type or ""
        max_bytes = settings.max_file_size_mb * 1024 * 1024

        if mime in _SUPPORTED_MIME_TYPES or path.suffix.lower() == ".pdf":
            file_size = path.stat().st_size
            if file_size > max_bytes:
                # Files larger than MAX_FILE_SIZE_MB are truncated rather than
                # rejected.  Classification accuracy may decrease for the
                # truncated portion, but we still extract useful metadata from
                # the document header/beginning.
                with open(path, "rb") as fh:
                    content_bytes = fh.read(max_bytes)
                parts = [
                    _CLASSIFICATION_PROMPT,
                    types.Part.from_bytes(
                        data=content_bytes,
                        mime_type=mime or "application/octet-stream",
                    ),
                ]
            else:
                uploaded = client.files.upload(file=str(path))
                parts = [_CLASSIFICATION_PROMPT, uploaded]
            response = client.models.generate_content(
                model=settings.gemini_flash_model,
                contents=parts,
            )

        elif path.suffix.lower() in _TEXT_EXTENSIONS:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text_content = fh.read(20_000)
            response = client.models.generate_content(
                model=settings.gemini_flash_model,
                contents=_CLASSIFICATION_PROMPT + "\n\nContenido del documento:\n" + text_content,
            )

        else:
            response = client.models.generate_content(
                model=settings.gemini_flash_model,
                contents=(
                    _CLASSIFICATION_PROMPT
                    + f"\n\nNombre del archivo: {file_index.name}"
                    + f"\nExtensión: {file_index.extension}"
                    + "\n[Contenido binario – clasifica únicamente por nombre/extensión]"
                ),
            )

        return _parse_response(response.text, file_index)

    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini classification failed for %s: %s", file_index.path, exc)
        return _stub_metadata(file_index)
