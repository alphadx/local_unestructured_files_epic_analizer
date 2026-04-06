from __future__ import annotations

"""
Gemini service – document classification, PII detection, and metadata extraction.

Uses the google-genai SDK (google.genai).  When the API key is not configured
(development / testing) the service returns safe stub objects so that the rest
of the pipeline can still function.
"""

import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.models.schemas import (
    DocumentCategory,
    DocumentEntities,
    DocumentMetadata,
    DocumentRelations,
    FileIndex,
    NamedEntity,
    NamedEntityType,
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
  "entidades_nombradas": [
    {"tipo": "<PERSON|ORGANIZATION|LOCATION|DATE|MONEY>", "valor": "<texto exacto>", "confianza": <0.0-1.0>}
  ],
  "fecha_emision": "<YYYY-MM-DD o null>",
  "periodo_fiscal": "<YYYY-MM o null>"
}
Reglas:
- Usa categorías conocidas; si no puedes inferir una válida, devuelve "Desconocido".
- `confianza_clasificacion` debe estar entre 0 y 1.
- `palabras_clave` debe contener como máximo 5 elementos únicos y no vacíos.
- `fecha_emision` debe usar formato YYYY-MM-DD o null.
- `periodo_fiscal` debe usar formato YYYY-MM o null.
- `entidades_nombradas` debe listar personas (PERSON), empresas/instituciones (ORGANIZATION),
  lugares/direcciones (LOCATION), fechas relevantes (DATE) y montos (MONEY) encontrados en el documento.
  No incluyas emails, RUTs ni teléfonos en este campo (se extraen por separado).
  Si no hay entidades semánticas, usa [].
- No incluyas ningún texto fuera del JSON.
"""

_RAG_PROMPT = """
Eres un asistente experto en análisis documental.
Responde usando únicamente el contexto proporcionado.
Si el contexto no contiene la respuesta, dilo explícitamente.
Mantén la respuesta breve, precisa y útil para auditoría.
"""


class _ClassificationEntities(BaseModel):
    emisor: str | None = None
    receptor: str | None = None
    monto_total: float | None = None
    moneda: str | None = None

    @field_validator("moneda", mode="before")
    @classmethod
    def _normalize_currency(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip().upper()
        return text or None


class _ClassificationRelations(BaseModel):
    id_licitacion_vinculada: str | None = None
    id_ot_referencia: str | None = None


class _ClassificationSemantic(BaseModel):
    resumen: str | None = None
    cluster_sugerido: str | None = None
    confianza_clasificacion: float = Field(default=0.0, ge=0.0, le=1.0)
    palabras_clave: list[str] = Field(default_factory=list)

    @field_validator("confianza_clasificacion", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> float:
        if value is None:
            return 0.0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, numeric))

    @field_validator("palabras_clave", mode="before")
    @classmethod
    def _normalize_keywords(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        keywords: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            keyword = re.sub(r"\s+", " ", str(item)).strip()
            if not keyword:
                continue
            key = keyword.lower()
            if key in seen:
                continue
            seen.add(key)
            keywords.append(keyword)
            if len(keywords) == 5:
                break
        return keywords


class _ClassificationPii(BaseModel):
    detected: bool = False
    risk_level: RiskLevel = RiskLevel.GREEN
    details: list[str] = Field(default_factory=list)

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalize_risk_level(cls, value: object) -> str | RiskLevel:
        if value is None:
            return RiskLevel.GREEN
        text = str(value).strip().lower()
        if text in {RiskLevel.GREEN.value, RiskLevel.YELLOW.value, RiskLevel.RED.value}:
            return text
        return RiskLevel.GREEN

    @field_validator("details", mode="before")
    @classmethod
    def _normalize_details(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


class _ClassificationPayload(BaseModel):
    categoria: str = DocumentCategory.UNKNOWN.value
    entidades: _ClassificationEntities = Field(default_factory=_ClassificationEntities)
    relaciones: _ClassificationRelations = Field(default_factory=_ClassificationRelations)
    analisis_semantico: _ClassificationSemantic = Field(default_factory=_ClassificationSemantic)
    pii_info: _ClassificationPii = Field(default_factory=_ClassificationPii)
    entidades_nombradas: list[dict] = Field(default_factory=list)
    fecha_emision: str | None = None
    periodo_fiscal: str | None = None

    @field_validator("categoria", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> str:
        if value is None:
            return DocumentCategory.UNKNOWN.value
        text = str(value).strip()
        return text or DocumentCategory.UNKNOWN.value

    @field_validator("fecha_emision", mode="before")
    @classmethod
    def _normalize_date(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None

    @field_validator("periodo_fiscal", mode="before")
    @classmethod
    def _normalize_period(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if re.fullmatch(r"\d{4}-\d{2}", text) else None


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


def _payload_to_metadata(payload: _ClassificationPayload, file_index: FileIndex) -> DocumentMetadata:
    try:
        categoria = DocumentCategory(payload.categoria)
    except ValueError:
        categoria = DocumentCategory.UNKNOWN

    _GEMINI_TYPE_MAP = {
        "PERSON": NamedEntityType.PERSON,
        "ORGANIZATION": NamedEntityType.ORGANIZATION,
        "LOCATION": NamedEntityType.LOCATION,
        "DATE": NamedEntityType.DATE,
        "MONEY": NamedEntityType.MONEY,
    }
    named_entities: list[NamedEntity] = []
    for item in payload.entidades_nombradas:
        tipo = str(item.get("tipo", "")).upper()
        valor = str(item.get("valor", "")).strip()
        if not valor or tipo not in _GEMINI_TYPE_MAP:
            continue
        try:
            confidence = float(item.get("confianza", 0.8))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.8
        named_entities.append(
            NamedEntity(
                entity_type=_GEMINI_TYPE_MAP[tipo],
                value=valor,
                confidence=confidence,
                source="gemini",
            )
        )

    return DocumentMetadata(
        documento_id=file_index.sha256 or file_index.path,
        file_index=file_index,
        categoria=categoria,
        entidades=DocumentEntities(
            emisor=payload.entidades.emisor,
            receptor=payload.entidades.receptor,
            monto_total=payload.entidades.monto_total,
            moneda=payload.entidades.moneda,
        ),
        relaciones=DocumentRelations(
            id_licitacion_vinculada=payload.relaciones.id_licitacion_vinculada,
            id_ot_referencia=payload.relaciones.id_ot_referencia,
        ),
        analisis_semantico=SemanticAnalysis(
            resumen=payload.analisis_semantico.resumen,
            cluster_sugerido=payload.analisis_semantico.cluster_sugerido,
            confianza_clasificacion=payload.analisis_semantico.confianza_clasificacion,
            palabras_clave=payload.analisis_semantico.palabras_clave,
        ),
        pii_info=PiiInfo(
            detected=payload.pii_info.detected,
            risk_level=payload.pii_info.risk_level,
            details=payload.pii_info.details,
        ),
        named_entities=named_entities,
        fecha_emision=payload.fecha_emision,
        periodo_fiscal=payload.periodo_fiscal,
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
    try:
        payload = _ClassificationPayload.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to validate Gemini JSON response: %s", exc)
        return _stub_metadata(file_index)

    return _payload_to_metadata(payload, file_index)


def _classify_with_text(file_index: FileIndex, text_content: str) -> DocumentMetadata:
    client = _get_client()
    prompt = (
        _CLASSIFICATION_PROMPT
        + "\n\nTexto extraído del documento:\n"
        + text_content[:12_000]
    )
    response = client.models.generate_content(
        model=settings.gemini_flash_model,
        contents=prompt,
    )
    return _parse_response(response.text, file_index)


def _enrich_with_regex_ner(metadata: DocumentMetadata, text: str) -> DocumentMetadata:
    """Run Layer 1 regex NER and merge results with any existing Gemini entities."""
    from app.services.ner_service import _deduplicate, _extract_regex_entities

    regex_entities = _extract_regex_entities(text)
    merged = _deduplicate(regex_entities + list(metadata.named_entities))
    metadata.named_entities = merged
    return metadata


def classify_document(file_index: FileIndex, extracted_text: str | None = None) -> DocumentMetadata:
    """
    Send a file to Gemini Flash for classification and metadata extraction.

    Falls back to a stub when the API key is absent or the call fails.
    Always runs regex NER (Layer 1) on available text content.
    """
    if not settings.gemini_api_key:
        logger.debug("Gemini API key not set – returning stub for %s", file_index.path)
        metadata = _stub_metadata(file_index)
        if extracted_text and extracted_text.strip():
            metadata = _enrich_with_regex_ner(metadata, extracted_text)
        return metadata

    if extracted_text and extracted_text.strip():
        metadata = _classify_with_text(file_index, extracted_text)
        return _enrich_with_regex_ner(metadata, extracted_text)

    from google.genai import types  # type: ignore

    client = _get_client()
    path = Path(file_index.path)

    try:
        mime = file_index.mime_type or ""
        max_bytes = settings.max_file_size_mb * 1024 * 1024
        text_for_ner: str = ""

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
                text_for_ner = fh.read(20_000)
            response = client.models.generate_content(
                model=settings.gemini_flash_model,
                contents=_CLASSIFICATION_PROMPT + "\n\nContenido del documento:\n" + text_for_ner,
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

        metadata = _parse_response(response.text, file_index)
        if text_for_ner:
            metadata = _enrich_with_regex_ner(metadata, text_for_ner)
        return metadata

    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini classification failed for %s: %s", file_index.path, exc)
        return _stub_metadata(file_index)


def generate_rag_answer(question: str, context: str) -> str | None:
    """Generate a grounded answer for a RAG query."""
    if not settings.gemini_api_key:
        return None

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=settings.gemini_flash_model,
            contents=f"{_RAG_PROMPT}\n\nPregunta:\n{question}\n\nContexto:\n{context}",
        )
        text = (response.text or "").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001
        logger.error("RAG generation failed: %s", exc)
        return None
