# skill: audit-security-retention

## When to use
Use when tasks touch API key auth, audit logs, job retention, or security-sensitive response handling.

## Inputs
- API key configuration.
- Audit entries.
- Retention limits.
- Endpoint access patterns.

## Procedure (step-by-step, deterministic)
1. Check the API key middleware in `backend/app/main.py`.
2. Keep `/health`, `/docs`, `/openapi.json`, and `/redoc` unauthenticated.
3. Record job, search, and reorganization operations through audit log helpers.
4. Apply retention pruning only to completed or failed jobs.
5. Prefer safe error messages for file moves and external service failures.

## Constraints (hard rules)
- Do not expose secrets in responses or logs.
- Do not bypass audit logging for significant user actions.
- Do not delete active job state.

## Output (structured)
- Access decision.
- Audit entry set.
- Retention action summary.

## Evidence Sources (files, modules, data)
- `backend/app/main.py`
- `backend/app/services/audit_log.py`
- `backend/app/services/job_manager.py`
- `backend/app/routers/audit.py`
- `backend/app/routers/admin.py`
- `tests/test_phase5_security.py`

## Anti-patterns
- Logging secrets or raw credentials.
- Treating audit logs as mutable history.
- Allowing pruning to remove running jobs.
