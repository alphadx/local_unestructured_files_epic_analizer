from __future__ import annotations

"""
Embeddings service – converts text to dense vectors using Gemini
via the google-genai SDK.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

FALLBACK_EMBEDDING_MODELS = [
    "models/gemini-embedding-001",
    "models/gemini-embedding-2-preview",
]


def _try_embed(model: str, text: str) -> list[float] | None:
    from google import genai  # type: ignore

    client = genai.Client(api_key=settings.gemini_api_key)
    result = client.models.embed_content(model=model, contents=text)
    return result.embeddings[0].values


def embed_text(text: str) -> list[float] | None:
    """
    Return a float vector for *text*, or None when Gemini is unavailable.
    """
    if not settings.gemini_api_key or not text.strip():
        return None

    attempt_models = [settings.gemini_embedding_model] + [m for m in FALLBACK_EMBEDDING_MODELS if m != settings.gemini_embedding_model]

    last_exc: Exception | None = None
    for model in attempt_models:
        try:
            logger.info("Intentando embedding con modelo=%s text_len=%d", model, len(text))
            return _try_embed(model, text)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.error(
                "Embedding failed for model=%s text_len=%d: %s",
                model,
                len(text),
                exc,
            )
            if "NOT_FOUND" not in str(exc):
                break
            logger.info("Intentando fallback de embeddings hacia otro modelo...")

    if last_exc is not None:
        logger.error("Embedding ultimately failed for all tried models. last error: %s", last_exc)
    return None


def embed_texts(texts: list[str]) -> list[list[float] | None]:
    """Batch-embed a list of texts."""
    return [embed_text(t) for t in texts]
