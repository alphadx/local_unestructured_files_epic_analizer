# skill: job-lifecycle

## When to use
Use when tasks affect job creation, status polling, logs, pruning, or pipeline orchestration.

## Inputs
- `ScanRequest`.
- Job status.
- Pipeline progress.
- Retention settings.

## Procedure (step-by-step, deterministic)
1. Create jobs through `backend/app/services/job_manager.py`.
2. Mark jobs as running before the pipeline executes.
3. Update progress and log entries during each pipeline phase.
4. Persist completed artifacts in the in-memory stores.
5. Prune finished jobs only through the retention policy path.

## Constraints (hard rules)
- Do not treat the job store as durable across restarts.
- Do not mark a job completed before the pipeline actually ends.
- Do not remove running jobs during pruning.

## Output (structured)
- `JobProgress`.
- Logs.
- Pruning summary.

## Evidence Sources (files, modules, data)
- `backend/app/services/job_manager.py`
- `backend/app/routers/jobs.py`
- `backend/app/models/schemas.py`
- `tests/test_api.py`
- `tests/test_phase5_security.py`

## Anti-patterns
- Directly mutating status without a pipeline step.
- Losing log subscription state during execution.
- Pruning without checking job state or age.
