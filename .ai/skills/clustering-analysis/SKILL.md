# skill: clustering-analysis

## When to use
Use when tasks affect semantic clustering, HDBSCAN fallback behavior, cluster labels, or family grouping.

## Inputs
- Documents with embeddings.
- Document categories and cluster suggestions.
- Optional `hdbscan` availability.

## Procedure (step-by-step, deterministic)
1. Read cluster candidates from `backend/app/services/clustering_service.py`.
2. Prefer embedding-based clustering when vectors are available.
3. Fall back to DBSCAN or label-based grouping if HDBSCAN is missing.
4. Build cluster labels from dominant semantic signals, not from arbitrary IDs.
5. Preserve family labeling and inconsistency detection for reports.

## Constraints (hard rules)
- Do not assume HDBSCAN is installed.
- Do not fail the pipeline when clustering libraries are missing.
- Do not lose document-to-cluster traceability.

## Output (structured)
- `Cluster` list.
- Cluster families.
- Inconsistency notes.

## Evidence Sources (files, modules, data)
- `backend/app/services/clustering_service.py`
- `backend/app/models/schemas.py`
- `backend/app/services/job_manager.py`
- `tests/test_clustering.py`

## Anti-patterns
- Hard-coding a single clustering algorithm.
- Creating clusters without document membership.
- Dropping fallback semantics when optional dependencies are absent.
