# Project Context

## Domain
- Intelligent unstructured-file ingestion and data governance.
- Focused on local or mounted directories plus optional Google Drive and SharePoint sources.
- Main outputs: document classification, PII detection, semantic embeddings, clustering, search, RAG, directory-group analysis, and file reorganization plans.

## Engineering Stack
- Backend: FastAPI 0.111 on Python 3.12.
- Frontend: Next.js 16.2, React 18.3, Tailwind CSS 4, D3, Axios.
- Storage: in-memory job store, optional ChromaDB vector store.
- Testing: pytest + pytest-asyncio in backend; Vitest + Testing Library in frontend.
- Deployment: Docker Compose with backend, frontend, and ChromaDB services.

## Operational Patterns
- Scans are read-only until the explicit reorganization endpoint is called.
- Jobs are async and polled through `/api/jobs/{job_id}` with live log websocket support.
- Filtering is configurable per job and system-wide by extension and MIME rules.
- Optional API-key middleware protects non-public endpoints.
- External services degrade gracefully when Gemini, ChromaDB, or optional clustering libraries are absent.

## Key Risks and Constraints
- Job state is in-memory and lost on restart.
- Vector store is ephemeral by default in compose.
- Gemini calls are optional but central to classification and embeddings.
- HDBSCAN is optional; clustering falls back to DBSCAN or label-based grouping.
- Reorganization can move files, so execution must remain explicitly user-approved.

## Evidence Sources
- `README.md`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/models/schemas.py`
- `backend/app/routers/`
- `backend/app/services/`
- `backend/app/db/vector_store.py`
- `docker-compose.yml`
- `tests/`
