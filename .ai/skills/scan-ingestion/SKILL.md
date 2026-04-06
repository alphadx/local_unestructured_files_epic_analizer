# skill: scan-ingestion

## When to use
Use when a task touches directory scanning, file indexing, duplicate detection, MIME detection, or per-job ingestion overrides.

## Inputs
- Scan target path or remote source request.
- `ScanRequest` fields.
- Current values from `app.config.settings`.

## Procedure (step-by-step, deterministic)
1. Validate that the path or source provider is supported by `backend/app/models/schemas.py`.
2. Resolve the effective ingestion mode and filter lists from request values or settings.
3. Scan through `backend/app/services/scanner.py` and keep the process read-only.
4. Preserve SHA-256 duplicate detection and MIME detection behavior.
5. Record skipped files through audit paths if filtering removes content.

## Constraints (hard rules)
- Never modify files during scanning.
- Never classify or embed files that were filtered out.
- Never assume hidden directories, executables, or temp files should be processed.

## Output (structured)
- `FileIndex` list.
- Filter statistics.
- Duplicate summary.

## Evidence Sources (files, modules, data)
- `backend/app/services/scanner.py`
- `backend/app/services/mime_filter.py`
- `backend/app/models/schemas.py`
- `backend/app/config.py`
- `tests/test_scanner.py`

## Anti-patterns
- Scanning with hard-coded rules that bypass `ScanRequest`.
- Treating file writes as part of ingestion.
- Skipping duplicate detection or MIME-based filtering.
