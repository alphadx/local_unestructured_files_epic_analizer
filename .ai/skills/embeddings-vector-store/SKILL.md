# skill: embeddings-vector-store

## When to use
Use when tasks touch embeddings, ChromaDB storage, semantic retrieval, or vector reset behavior.

## Inputs
- Text to embed.
- `DocumentMetadata` or `DocumentChunk` with embeddings.
- Vector store configuration.

## Procedure (step-by-step, deterministic)
1. Resolve the configured embedding model from `backend/app/config.py`.
2. Generate embeddings through `backend/app/services/embeddings_service.py`.
3. Upsert document or chunk vectors through `backend/app/db/vector_store.py`.
4. Query via cosine similarity only when vectors exist.
5. Treat unavailable ChromaDB as a graceful no-op, not a failure cascade.

## Constraints (hard rules)
- Never assume the vector store is persistent.
- Never require ChromaDB for core job completion.
- Never store embeddings outside the schema fields already excluded from API output.

## Output (structured)
- Embedding vectors.
- Upsert result or no-op status.
- Similarity query hits.

## Evidence Sources (files, modules, data)
- `backend/app/services/embeddings_service.py`
- `backend/app/db/vector_store.py`
- `backend/app/models/schemas.py`
- `backend/app/config.py`
- `tests/test_vector_store.py`

## Anti-patterns
- Treating vector persistence as guaranteed.
- Coupling search success to ChromaDB availability.
- Storing raw embeddings in API-visible payloads.
