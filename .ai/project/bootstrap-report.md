# Bootstrap Report

## What was detected
- A FastAPI backend that orchestrates scan, classification, embedding, clustering, reporting, search, RAG, audit, and reorganization workflows.
- A Next.js dashboard that consumes the backend through tabs for jobs, clusters, groups, audit, exploration, search, and RAG.
- Optional external services for Gemini, ChromaDB, Google Drive, and SharePoint.
- Read-only scan semantics with explicit execution for file moves.

## What was generated
- A factual project context file for agent grounding.
- Five execution-role agents: planner, executor, verifier, critic, retriever.
- Twelve focused skills tied to the real backend and frontend flows.
- A hook manifest for planning, execution, response, and learning governance.
- A tool-capability manifest for search, repository access, test execution, and build checks.

## Assumptions made
- No dedicated MCP server exists in the repo, so tool contracts are documented as workspace capabilities rather than live MCP endpoints.
- No database migrations or persistent relational store were detected, so the layer treats persistence as in-memory plus optional ChromaDB.

## Risks
- The job store and vector store are not durable by default.
- Some flows depend on optional packages that may be absent in local environments.
- The repo does not show CI workflows, so verification must rely on local tests and explicit checks.

## Suggested next steps
- Keep `.ai/project/context.md` synchronized with any endpoint or schema changes.
- Add CI-backed verification if a workflow is introduced later.
- Expand the hook layer only if new safety constraints appear in the pipeline.
