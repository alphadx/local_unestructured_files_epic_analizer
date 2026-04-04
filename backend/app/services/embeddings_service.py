from __future__ import annotations

"""
Embeddings service – converts text to dense vectors using Gemini
text-embedding-004 via the google-genai SDK.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def embed_text(text: str) -> list[float] | None:
    """
    Return a float vector for *text*, or None when Gemini is unavailable.
    """
    if not settings.gemini_api_key or not text.strip():
        return None

    try:
        from google import genai  # type: ignore

        client = genai.Client(api_key=settings.gemini_api_key)
        result = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
        )
        return result.embeddings[0].values
    except Exception as exc:  # noqa: BLE001
        logger.error("Embedding failed: %s", exc)
        return None


def embed_texts(texts: list[str]) -> list[list[float] | None]:
    """Batch-embed a list of texts."""
    return [embed_text(t) for t in texts]
