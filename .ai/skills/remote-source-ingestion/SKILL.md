# skill: remote-source-ingestion

## When to use
Use when tasks affect Google Drive or SharePoint ingestion, temporary download staging, or remote path rewriting.

## Inputs
- `SourceProvider`.
- `source_options`.
- Remote credential settings.
- Target path.

## Procedure (step-by-step, deterministic)
1. Validate remote source requirements from `backend/app/models/schemas.py`.
2. Resolve Google Drive or SharePoint credentials from request or settings.
3. Download content to a temporary directory only for scan preparation.
4. Rewrite paths back to remote-prefixed identifiers after scanning.
5. Clean up through the source service helpers.

## Constraints (hard rules)
- Do not require remote credentials for local scans.
- Do not pretend remote download succeeded if credential validation fails.
- Do not expose token material in logs or outputs.

## Output (structured)
- Temporary scan root.
- Remote path prefix.
- Validation errors when credentials are missing.

## Evidence Sources (files, modules, data)
- `backend/app/services/source_service.py`
- `backend/app/models/schemas.py`
- `backend/app/routers/jobs.py`
- `tests/test_source_service.py`

## Anti-patterns
- Mixing local and remote path semantics.
- Leaving remote credentials unvalidated.
- Logging service account JSON or access tokens.
