# Production Readiness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate confirmed Phase 8A business-logic defects from the production-readiness audit, add regression coverage, and re-verify hidden/internal operational honesty without broadening product scope beyond Phase 8A.

**Architecture:** The remediation keeps the existing Phase 8A product boundary but hardens three critical invariants: server-enforced identity/visibility, append-only frozen assessment and valuation lineage, and safe upstream lineage from listings through clusters and sites. Where the current schema makes destructive or drifting behavior unavoidable, add focused Alembic changes and migrate read paths to explicit frozen IDs instead of latest-state lookups.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic, Postgres/PostGIS, Next.js App Router, TypeScript, pytest, Ruff, npm lint/typecheck/build, docker compose.

---

## Scope Split

- **Business-logic remediation:** Fix confirmed P0/P1/P2 defects affecting correctness, frozen artifact integrity, visibility/redaction honesty, lineage safety, provenance stability, and job recovery.
- **Local/dev fixture validation:** Re-run backend/frontend checks and local fixture workflows as far as the environment honestly allows.
- **Hidden/internal readiness:** Reassess whether the hidden/internal operating mode is honest and auditable after fixes.
- **Visible rollout readiness:** Keep separate. Visible probability remains deferred unless re-verification proves the repo honestly supports it within the controlling spec.

## Root-Cause Backlog

### 1. Caller-asserted authority and visibility

- Prior leads:
  - request-supplied `viewer_role` / `actor_role` drives hidden/admin behavior
  - standard-mode redaction is inconsistent and leaks hidden economics
- Primary modules:
  - `services/api/app/dependencies.py`
  - `services/api/app/routes/assessments.py`
  - `services/api/app/routes/opportunities.py`
  - `services/api/app/routes/admin.py`
  - `python/landintel/review/visibility.py`
  - `python/landintel/review/overrides.py`
  - `services/web/app/api/[...path]/route.ts`
  - `services/web/lib/auth/*`
  - `services/web/lib/landintel-api.ts`
- Remediation intent:
  - derive effective role from server-side request/session context
  - treat request flags only as mode hints, never as authority
  - close all standard-read leaks for hidden/internal economics

### 2. Frozen artifact mutability and replay drift

- Prior leads:
  - assessment rows are refreshed in place
  - valuation runs/results are refreshed in place
  - readback/export/replay use latest valuation state instead of frozen IDs
- Primary modules:
  - `python/landintel/assessments/service.py`
  - `python/landintel/services/assessments_readback.py`
  - `python/landintel/services/opportunities_readback.py`
  - `python/landintel/review/visibility.py`
  - `python/landintel/review/audit_export.py`
  - `python/landintel/review/overrides.py`
  - `python/landintel/valuation/service.py`
  - `python/landintel/domain/models.py`
  - `db/migrations/*`
- Remediation intent:
  - freeze assessment and valuation artifact identity
  - bind replay/readback/export to the exact frozen ledger and valuation IDs
  - ensure reruns create new immutable lineage rather than rewriting originals

### 3. Destructive lineage and provenance drift

- Prior leads:
  - cluster rebuild deletes cluster rows and can cascade-delete site lineage
  - planning/reference imports repoint current support tables to newer snapshots
  - unsafe `source_name` values can influence storage keys
- Primary modules:
  - `python/landintel/listings/service.py`
  - `python/landintel/jobs/service.py`
  - `python/landintel/planning/import_common.py`
  - `python/landintel/planning/*bootstrap*`
  - `python/landintel/domain/models.py`
  - `db/migrations/*`
- Remediation intent:
  - make reclustering non-destructive to site/scenario/assessment lineage
  - preserve snapshot provenance where PIT/replay depends on it
  - bound and sanitize source identifiers before storage path construction

### 4. Worker recovery and idempotency gaps

- Prior leads:
  - stale `RUNNING` jobs are not reclaimed
  - storage side effects can happen before DB commit without reconciliation
- Primary modules:
  - `python/landintel/jobs/service.py`
  - `services/worker/app/main.py`
  - `python/landintel/storage/local.py`
  - `python/landintel/storage/supabase.py`
  - connector persistence paths in `python/landintel/listings/service.py`
- Remediation intent:
  - reclaim or safely recycle stale running jobs
  - make storage writes and DB persistence retry-safe and reconcilable

### 5. Docs/runtime truth drift

- Prior leads:
  - setup script success reporting was overstated
  - docs claim stronger immutability/replay guarantees than current code delivered
- Primary modules:
  - `README.md`
  - `docs/guides/local-usage.md`
  - `docs/operations/deployment.md`
  - `docs/operations/runbook.md`
  - `scripts/setup_local.sh`
- Remediation intent:
  - align docs to actual guarantees after code fixes
  - keep remaining limitations explicit and separate from fixed defects

## Migration Strategy

- If cluster-site lineage or frozen valuation binding requires schema changes:
  - add a focused Alembic migration in `db/migrations/versions/`
  - prefer additive columns / FK changes over broad rewrites
  - preserve existing data by backfilling explicit frozen IDs where possible
- Expected likely migration areas:
  - site linkage away from destructive `listing_cluster_id` cascade semantics
  - frozen assessment -> valuation binding columns if current ledger/result linkage is insufficient
  - provenance/version tables only if current current-state tables cannot preserve PIT-safe references

## Re-Verification Matrix Before Code Changes

For each prior audit lead:

- expected behavior from spec/docs
- actual current behavior
- exact code path
- minimal reproduction
- verdict: `CONFIRMED`, `DISPROVED`, or `PARTIALLY_CONFIRMED`

Target leads to re-verify immediately:

1. cluster rebuild / site lineage destruction
2. caller-asserted auth and role gating
3. mutable assessment artifacts
4. mutable valuation artifacts and latest-state drift
5. standard-mode hidden economics leak
6. unsafe `source_name` handling
7. provenance drift in planning/reference imports
8. stale `RUNNING` jobs and storage-before-DB recovery gaps
9. `setup_local.sh` truthfulness regression check

## Testing Strategy

### Auth / visibility / redaction

- Add API tests proving forged `viewer_role` / `actor_role` values do not escalate privileges.
- Add web-proxy-aware tests where possible to ensure server-side session role, not query params, determines visibility.
- Add analyst vs reviewer/admin regression tests for assessment detail and opportunities in standard and hidden modes.

### Frozen assessment / valuation lineage

- Add tests proving reruns do not mutate original feature snapshot, evidence rows, result rows, comparable sets, ledger rows, or valuation rows.
- Add tests proving historical assessment readback remains stable after later valuation activity or overrides.
- Add replay verification tests pinned to frozen IDs/hashes.

### Cluster/site lineage and provenance

- Add tests proving reclustering does not delete or orphan site/scenario/assessment lineage.
- Add tests for any migration/backfill behavior.
- Add tests proving historical provenance links remain stable when newer planning/reference datasets are imported.

### Source-name safety and worker recovery

- Add traversal/unsafe-character tests for manual URL and CSV source identifiers.
- Add stale `RUNNING` job recovery tests.
- Add retry/idempotency tests for connector persistence and raw-asset reconciliation.

### Runtime validation

- Re-run:
  - `ruff check .`
  - `pytest`
  - `cd services/web && npm run lint`
  - `cd services/web && npm run typecheck`
  - `cd services/web && npm run build`
- Then attempt:
  - `docker compose up --build -d`
  - `docker compose ps`
  - `bash scripts/setup_local.sh`
  - `alembic upgrade head` against reachable Postgres/PostGIS
  - curl/API flow validation
  - browser validation for analyst / reviewer / admin flows

## Execution Workstreams

### Workstream A: Auth / Role / Visibility

- Re-verify all caller-asserted authority paths.
- Implement request-scoped server-side role resolution.
- Remove request-supplied authority from business logic.
- Close standard-mode economics leaks.
- Update docs/tests.

### Workstream B: Frozen Assessment / Replay / Valuation

- Re-verify mutability and drift paths.
- Refactor assessment creation/rerun semantics to preserve immutability.
- Refactor valuation lineage to remain immutable and frozen-ID-bound.
- Update replay/readback/export/opportunity paths.
- Update docs/tests.

### Workstream C: Lineage / Provenance / Recovery

- Re-verify reclustering destruction, provenance drift, source-name safety, and stale job recovery.
- Add schema/data fixes where needed.
- Harden connector persistence and job reclaim behavior.
- Update docs/tests.
- Current slice ownership:
  - non-destructive cluster rebuild with site relink and lineage audit
  - storage-path source-name sanitization
  - stale `RUNNING` job reclaim logic

### Workstream D: Verification / Docs / Runtime

- Maintain remediation matrix while fixes land.
- Re-run targeted tests after each material change.
- Re-run full validation baseline.
- Execute runtime checks as far as the environment permits.
- Align docs to actual behavior.

### Workstream E: Independent Final Re-Review

- Fresh agents with no implementation ownership re-check:
  - role gating bypass attempts
  - hidden-field leakage
  - cluster/site lineage safety
  - frozen artifact drift
  - valuation/readback drift
  - docs vs actual behavior

## Final Re-Review Plan

- Use fresh independent agents only after implementation and verification are complete.
- Require explicit pass/fail findings, not summaries.
- Any new P0/P1/P2 findings reopen implementation before final signoff.

## Exit Criteria

- Every confirmed prior-audit P0/P1/P2 issue is fixed or explicitly disproved with tests and code-path evidence.
- Regression tests cover every fixed defect class.
- Docs are aligned to actual Phase 8A guarantees.
- Full validation baseline passes.
- Runtime validation is attempted seriously and any environment blockers are documented precisely.
- Independent re-review is completed.
