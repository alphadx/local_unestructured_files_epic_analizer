# skill: rag-answering

## When to use
Use when tasks affect `/api/rag/query`, retrieval context building, answer generation, or source attribution.

## Inputs
- User query.
- Optional job filter.
- Top-k setting.
- Available documents, chunks, and embeddings.

## Procedure (step-by-step, deterministic)
1. Retrieve context candidates from vector search or fallback lexical ranking.
2. Deduplicate hits by source ID.
3. Build a bounded context window with the most relevant sources first.
4. Call Gemini answer generation only when the caller requests an answer.
5. Return the final answer plus source metadata.

## Constraints (hard rules)
- Do not exceed the context budget.
- Do not fabricate sources that were not retrieved.
- Do not return an empty query without validation.

## Output (structured)
- Answer text or null.
- Context block.
- Source list with scores and distances.

## Evidence Sources (files, modules, data)
- `backend/app/services/rag_service.py`
- `backend/app/routers/rag.py`
- `backend/app/db/vector_store.py`
- `backend/app/services/embeddings_service.py`
- `backend/app/services/gemini_service.py`

## Anti-patterns
- Answering without citations from retrieved sources.
- Ignoring the context cap.
- Returning unvalidated sources from stale caches.
