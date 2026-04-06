# skill: dashboard-insights

## When to use
Use when tasks affect the Next.js dashboard, tabs, insight loading, filters, charts, or job status UI.

## Inputs
- Frontend state.
- API responses from jobs, reports, search, audit, and RAG.
- Filter configuration.

## Procedure (step-by-step, deterministic)
1. Read the current dashboard state from `frontend/src/app/page.tsx`.
2. Match UI controls to backend contracts and Pydantic schemas.
3. Keep loading and error states aligned with async job polling.
4. Preserve tab-specific data loading and filter overrides.
5. Update tests when component contracts change.

## Constraints (hard rules)
- Do not invent frontend state that the backend cannot satisfy.
- Do not remove progress or error feedback from long-running jobs.
- Do not break tab contracts for dashboard, clusters, groups, audit, exploration, search, or rag.

## Output (structured)
- Updated UI state flow.
- Component contract notes.
- Frontend verification targets.

## Evidence Sources (files, modules, data)
- `frontend/src/app/page.tsx`
- `frontend/src/components/FilterConfiguration.tsx`
- `frontend/src/components/ClusterMap.tsx`
- `frontend/src/components/JobStatusCard.tsx`
- `frontend/src/components/GroupAnalysis.tsx`
- `frontend/src/components/StatisticsCharts.tsx`
- `frontend/src/lib/api.ts`

## Anti-patterns
- Hard-coding backend assumptions into components.
- Dropping error handling for async insight loads.
- Breaking existing tabs while adding new visualizations.
