# skill: filter-governance

## When to use
Use when changing whitelist/blacklist behavior, MIME rules, extension lists, or filter statistics.

## Inputs
- `ingestion_mode`.
- Allowed and denied extensions.
- Allowed and denied MIME prefixes.
- Filter audit entries.

## Procedure (step-by-step, deterministic)
1. Read the system defaults from `backend/app/config.py`.
2. Read request overrides from `ScanRequest`.
3. Apply the same rules in scanner, admin endpoint, and frontend form.
4. Keep whitelist mode strict and blacklist mode permissive.
5. Verify rejected files are recorded in audit output.

## Constraints (hard rules)
- Do not process binary or executable content when the rule set excludes it.
- Do not diverge between backend filtering and frontend filter configuration.
- Do not hide filter decisions from audit endpoints.

## Output (structured)
- Effective filter configuration.
- Accepted file list.
- Rejected file list with reasons.

## Evidence Sources (files, modules, data)
- `backend/app/config.py`
- `backend/app/services/mime_filter.py`
- `backend/app/routers/admin.py`
- `frontend/src/components/FilterConfiguration.tsx`
- `tests/test_api.py`

## Anti-patterns
- Maintaining separate filter logic in different layers.
- Using ad hoc file-extension checks without MIME support.
- Forgetting to record filter decisions for audits.
