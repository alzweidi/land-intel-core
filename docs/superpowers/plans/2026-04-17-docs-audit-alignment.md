# Documentation Audit Alignment Plan

**Goal:** Bring repository documentation into line with the current Phase 8A codebase, with emphasis on the actual local workflow, route availability, role gating, operational surfaces, and documentation taxonomy.

## Assumptions

- The controlling Phase 8A spec remains authoritative, but implementation-facing docs must describe the current runtime truth.
- Historical execution plans may stay as archive material, but they should not be presented as current operator guidance.
- Placeholder UI shells should be called out clearly and removed from canonical workflow docs where they could mislead users.

## Workstreams

### 1. Audit runtime-facing docs
- Verify `README.md`, `docs/README.md`, `docs/guides/local-usage.md`, `docs/operations/deployment.md`, `docs/operations/runbook.md`, and `infra/compose/README.md` against:
  - current FastAPI routes
  - current Next.js routes and role gating
  - current local auth/session behavior
  - current scripts and env vars

### 2. Correct drift and inconsistencies
- Update route maps, command examples, auth notes, hidden-mode notes, and operational descriptions where the docs are incomplete or inaccurate.
- Distinguish operational surfaces from placeholder/shell-only UI routes.
- Expand API and service references where the code now exposes more than the docs describe.

### 3. Archive or reclassify stale documentation
- Reclassify historical implementation-plan material so it is clearly separate from current operator/runtime guidance.
- Update documentation indexes so readers land on the current canonical docs first.

### 4. Verify
- Re-read updated docs for internal consistency.
- Spot-check referenced paths, scripts, and route names against the repo.
- Run a lightweight diff review to confirm the changes are documentation-only and intentional.
