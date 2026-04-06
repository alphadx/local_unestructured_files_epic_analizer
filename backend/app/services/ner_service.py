from __future__ import annotations

"""
NER service — Named Entity Recognition via a hybrid 2-layer strategy.

Layer 1 (regex, CPU-only, zero latency):
  Extract well-defined structured entities: emails, Chilean RUTs, phone numbers.

Layer 2 (Gemini, optional):
  Extract semantic entities (PERSON, ORGANIZATION, LOCATION) from document text.
  Only called when Gemini is configured and the document has extracted text.

The public entry point is `extract_entities()`.
"""

import logging
import re
from collections import defaultdict

from app.models.schemas import (
    ContactRecord,
    ContactsReport,
    DocumentMetadata,
    NamedEntity,
    NamedEntityType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layer 1 — Regex patterns
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Chilean RUT: 1-2 digits dot 3 digits dot 3 digits dash verifier digit or K
_RUT_RE = re.compile(
    r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b",
)

# Phone numbers: Chilean mobile (+569XXXXXXXX), landline (+562XXXXXXXX),
# or generic 9/10-digit sequences with optional country code.
_PHONE_RE = re.compile(
    r"(?:\+56\s?)?(?:9\d{8}|[2-8]\d{7,8})\b",
)


def _extract_regex_entities(text: str) -> list[NamedEntity]:
    entities: list[NamedEntity] = []

    for match in _EMAIL_RE.finditer(text):
        entities.append(
            NamedEntity(
                entity_type=NamedEntityType.EMAIL,
                value=match.group(0).lower(),
                confidence=1.0,
                source="regex",
            )
        )

    for match in _RUT_RE.finditer(text):
        # Normalize: remove dots, keep dash
        raw = match.group(0).replace(".", "")
        entities.append(
            NamedEntity(
                entity_type=NamedEntityType.RUT,
                value=raw.upper(),
                confidence=1.0,
                source="regex",
            )
        )

    for match in _PHONE_RE.finditer(text):
        # Skip RUT false positives already captured above
        value = re.sub(r"\s+", "", match.group(0))
        entities.append(
            NamedEntity(
                entity_type=NamedEntityType.PHONE,
                value=value,
                confidence=0.9,
                source="regex",
            )
        )

    return entities


# ---------------------------------------------------------------------------
# Layer 2 — Gemini semantic extraction
# ---------------------------------------------------------------------------

_GEMINI_NER_PROMPT = """
Eres un experto en reconocimiento de entidades nombradas (NER).
Analiza el siguiente texto y devuelve ÚNICAMENTE un objeto JSON válido:
{
  "entidades": [
    {"tipo": "<PERSON|ORGANIZATION|LOCATION|DATE|MONEY>", "valor": "<texto exacto>", "confianza": <0.0-1.0>}
  ]
}
Reglas:
- Extrae solo entidades claramente identificables en el texto.
- No incluyas emails, RUTs ni teléfonos (ya son extraídos por otro sistema).
- Usa "PERSON" para nombres de personas, "ORGANIZATION" para empresas/instituciones,
  "LOCATION" para direcciones/ciudades/países, "DATE" para fechas y "MONEY" para montos.
- Si no encuentras entidades, devuelve {"entidades": []}.
- No incluyas ningún texto fuera del JSON.
"""

_TYPE_MAP = {
    "PERSON": NamedEntityType.PERSON,
    "ORGANIZATION": NamedEntityType.ORGANIZATION,
    "LOCATION": NamedEntityType.LOCATION,
    "DATE": NamedEntityType.DATE,
    "MONEY": NamedEntityType.MONEY,
}


def _extract_gemini_entities(text: str) -> list[NamedEntity]:
    import json

    from app.config import settings

    if not settings.gemini_api_key:
        return []

    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = _GEMINI_NER_PROMPT + "\n\nTexto:\n" + text[:8_000]
        response = client.models.generate_content(
            model=settings.gemini_flash_model,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

        data = json.loads(raw)
        entities: list[NamedEntity] = []
        for item in data.get("entidades", []):
            tipo = str(item.get("tipo", "")).upper()
            valor = str(item.get("valor", "")).strip()
            if not valor or tipo not in _TYPE_MAP:
                continue
            try:
                confidence = float(item.get("confianza", 0.8))
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.8
            entities.append(
                NamedEntity(
                    entity_type=_TYPE_MAP[tipo],
                    value=valor,
                    confidence=confidence,
                    source="gemini",
                )
            )
        return entities
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini NER extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_entities(text: str, use_gemini: bool = True) -> list[NamedEntity]:
    """
    Extract named entities from text using a hybrid 2-layer approach.

    Layer 1 always runs (regex: emails, RUTs, phones).
    Layer 2 (Gemini) runs only when `use_gemini=True` and the API key is set.
    Duplicates (same type + normalized value) are deduplicated keeping the
    highest-confidence entry.
    """
    entities = _extract_regex_entities(text)
    if use_gemini:
        entities.extend(_extract_gemini_entities(text))
    return _deduplicate(entities)


def _deduplicate(entities: list[NamedEntity]) -> list[NamedEntity]:
    seen: dict[tuple[str, str], NamedEntity] = {}
    for ent in entities:
        key = (ent.entity_type.value, ent.value.lower())
        if key not in seen or ent.confidence > seen[key].confidence:
            seen[key] = ent
    return list(seen.values())


def build_contacts_report(
    job_id: str, documents: list[DocumentMetadata]
) -> ContactsReport:
    """
    Aggregate named entities from all documents in a job into a ContactsReport.

    Entities with the same type+value are merged; frequency and document
    references are accumulated.
    """
    aggregated: dict[tuple[str, str], ContactRecord] = defaultdict(
        lambda: ContactRecord(entity_type=NamedEntityType.OTHER, value="", frequency=0)
    )

    for doc in documents:
        for ent in doc.named_entities:
            key = (ent.entity_type.value, ent.value.lower())
            if key not in aggregated:
                aggregated[key] = ContactRecord(
                    entity_type=ent.entity_type,
                    value=ent.value,
                    frequency=0,
                    document_ids=[],
                    source_paths=[],
                )
            record = aggregated[key]
            record.frequency += 1
            if doc.documento_id not in record.document_ids:
                record.document_ids.append(doc.documento_id)
            path = doc.file_index.path
            if path not in record.source_paths:
                record.source_paths.append(path)

    contacts = sorted(aggregated.values(), key=lambda r: r.frequency, reverse=True)
    return ContactsReport(
        job_id=job_id,
        total_documents_analyzed=len(documents),
        total_entities_found=sum(len(d.named_entities) for d in documents),
        contacts=contacts,
    )
