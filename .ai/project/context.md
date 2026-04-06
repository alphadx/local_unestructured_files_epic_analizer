# Project Context

## Domain
- Intelligent unstructured-file ingestion and data governance.
- Focused on local or mounted directories plus optional Google Drive and SharePoint sources.
- Main outputs: document classification, PII detection, semantic embeddings, clustering, search, RAG, directory-group analysis, file reorganization plans, and **named entity extraction (NER)**.

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
- NER pipeline is hybrid: Layer 1 (regex) extracts emails/RUTs/phones without any API call; Layer 2 (Gemini) extracts PERSON/ORG/LOC/DATE/MONEY during classification.

## Key Schemas (backend/app/models/schemas.py)
- `FileIndex` — raw file metadata (path, sha256, mime_type, etc.)
- `DocumentMetadata` — AI-enriched document record; includes `categoria`, `entidades`, `analisis_semantico`, `pii_info`, **`named_entities: list[NamedEntity]`**
- `NamedEntityType` — enum: PERSON, ORGANIZATION, LOCATION, EMAIL, PHONE, RUT, DATE, MONEY, OTHER
- `NamedEntity` — single entity with `entity_type`, `value`, `confidence`, `source` (regex|gemini)
- `ContactRecord` — aggregated entity view with `frequency` and `document_ids`
- `ContactsReport` — job-level summary of all named entities

## Key Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/jobs` | Start a new scan job |
| GET | `/api/jobs/{job_id}` | Poll job status |
| GET | `/api/jobs/{job_id}/logs/ws` | Live log WebSocket |
| POST | `/api/search` | Hybrid search (BM25 + embeddings) |
| POST | `/api/rag/query` | RAG grounded answer |
| GET | `/api/reports/{job_id}` | Full health report |
| GET | `/api/reports/{job_id}/documents` | Classified documents (with `named_entities`) |
| GET | `/api/reports/{job_id}/contacts` | Aggregated NER contacts (filter by `entity_type`, `min_frequency`) |
| GET | `/api/reports/{job_id}/statistics` | Distribution statistics |
| GET | `/api/reports/{job_id}/exploration` | Corpus exploration metrics |
| GET | `/api/reports/{job_id}/groups` | Directory group analysis |
| GET | `/api/reports/{job_id}/export/json` | Export as JSON |
| GET | `/api/reports/{job_id}/export/csv` | Export as CSV |
| GET | `/api/reports/{job_id}/executive-summary/pdf` | PDF executive summary |
| GET | `/api/admin/filter-config` | Current filter configuration |
| GET | `/api/admin/filter-stats` | Filter audit statistics |

## Key Risks and Constraints
- Job state is in-memory and lost on restart.
- Vector store is ephemeral by default in compose.
- Gemini calls are optional but central to classification and embeddings.
- HDBSCAN is optional; clustering falls back to DBSCAN or label-based grouping.
- Reorganization can move files, so execution must remain explicitly user-approved.

## Evidence Sources
- `README.md`
- `USAGE_EXAMPLES.md`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/models/schemas.py`
- `backend/app/routers/`
- `backend/app/services/`
- `backend/app/services/ner_service.py` — NER hybrid pipeline (Layer 1 regex + Layer 2 Gemini)
- `backend/app/services/gemini_service.py` — classification + NER extraction via `entidades_nombradas`
- `backend/app/db/vector_store.py`
- `docker-compose.yml`
- `tests/`
