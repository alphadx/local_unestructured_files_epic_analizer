# skill: search-hybrid

## When to use
Use when tasks affect `/api/search`, lexical matching, semantic search, faceting, or query filters.

## Inputs
- Search query.
- Scope.
- Category, extension, and directory filters.
- Job scope.

## Procedure (step-by-step, deterministic)
1. Load the query contract from `backend/app/models/schemas.py`.
2. Query documents and chunks from the in-memory job store.
3. Apply lexical and metadata filters before ranking.
4. Add semantic hits only when embeddings are available.
5. Return ranked results with facets and suggestions.

## Constraints (hard rules)
- Do not return results outside the requested scope.
- Do not ignore category, extension, or directory filters.
- Do not assume a vector hit is valid if the underlying document is missing.

## Output (structured)
- Ranked search results.
- Facets for categories, extensions, and directories.
- Search suggestions.

## Evidence Sources (files, modules, data)
- `backend/app/services/search_service.py`
- `backend/app/routers/search.py`
- `backend/app/models/schemas.py`
- `backend/app/services/job_manager.py`
- `tests/test_api.py`

## Anti-patterns
- Ranking without filter enforcement.
- Returning duplicate source IDs.
- Treating semantic search as mandatory for every request.
