# skill: reorganization-execution

## When to use
Use when tasks affect `/api/reorganize/{job_id}/execute` or the file move workflow.

## Inputs
- Completed report with a reorganization plan.
- Current filesystem state.
- User approval to execute moves.

## Procedure (step-by-step, deterministic)
1. Verify that the job report exists and has a plan in `backend/app/routers/reorganize.py`.
2. Resolve each source and destination path.
3. Create destination parents before moving files.
4. Move one file at a time and collect success or failure per action.
5. Record the outcome to audit logs.

## Constraints (hard rules)
- Do not execute the move path unless the user explicitly requests it.
- Do not modify source files during scan-only flows.
- Do not stop the whole batch when one move fails.

## Output (structured)
- Move summary.
- Error list.
- Audit record.

## Evidence Sources (files, modules, data)
- `backend/app/routers/reorganize.py`
- `backend/app/services/job_manager.py`
- `backend/app/services/audit_log.py`
- `backend/app/models/schemas.py`
- `tests/test_phase5_security.py`

## Anti-patterns
- Executing file moves without explicit approval.
- Dropping partial-success details.
- Treating failures as silent no-ops.
