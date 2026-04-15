# Phase 8A Controls And Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Phase 8A safety and control-plane layer: audited overrides, scoped visibility gating, kill switches, health/admin readback, and audit export without broadening visible probability by default.

**Architecture:** Extend the existing assessment, release, and audit model instead of introducing new infrastructure. Keep hidden scoring as the default runtime path, add explicit visibility gates and incidents as small control-plane records, and preserve original frozen assessment/valuation artifacts while layering overrides and redaction state on readback.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres job queue, Pydantic, Next.js/TypeScript, existing storage abstraction.

---

## File Structure

- Modify: `python/landintel/domain/enums.py`
- Modify: `python/landintel/domain/models.py`
- Modify: `python/landintel/domain/schemas.py`
- Create: `db/migrations/versions/20260415_000009_phase8a_controls_visibility.py`
- Create: `python/landintel/review/overrides.py`
- Create: `python/landintel/review/visibility.py`
- Create: `python/landintel/review/audit_export.py`
- Modify: `python/landintel/services/assessments_readback.py`
- Modify: `python/landintel/services/opportunities_readback.py`
- Modify: `python/landintel/services/model_releases_readback.py`
- Modify: `python/landintel/monitoring/health.py`
- Modify: `python/landintel/jobs/service.py`
- Create: `services/worker/app/jobs/health.py`
- Modify: `services/worker/app/jobs/connectors.py`
- Modify: `services/api/app/routes/assessments.py`
- Modify: `services/api/app/routes/admin.py`
- Modify: `services/api/app/routes/opportunities.py`
- Modify: `services/web/lib/landintel-api.ts`
- Modify: `services/web/app/assessments/[assessmentId]/page.tsx`
- Modify: `services/web/app/review-queue/page.tsx`
- Modify: `services/web/app/admin/health/page.tsx`
- Modify: `services/web/app/admin/model-releases/page.tsx`
- Create: `services/web/components/assessment-override-panel.tsx`
- Test: `tests/test_controls_phase8a.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

## Major Assumptions

- Local/dev remains hidden-only by default; any visible scope enablement is reviewer/admin-only fixture signoff, not a claim of broader readiness.
- Override support stays deliberately narrow in Phase 8A: valuation basis correction, assumption selection, reviewer disposition, and ranking suppression/display block only.
- Health dashboards stay API/readback-driven summaries, not heavy observability infrastructure.

### Task 1: Schema And Control-Plane Records

**Files:**
- Create: `db/migrations/versions/20260415_000009_phase8a_controls_visibility.py`
- Modify: `python/landintel/domain/enums.py`
- Modify: `python/landintel/domain/models.py`
- Modify: `python/landintel/domain/schemas.py`

- [ ] Add minimal canonical Phase 8A records:
  - `assessment_override`
  - `visibility_gate_result`
  - `incident_record`
  - `audit_export`
- [ ] Extend release-scope state with explicit visibility modes:
  - `DISABLED`
  - `HIDDEN_ONLY`
  - `VISIBLE_REVIEWER_ONLY`
- [ ] Preserve immutable links to:
  - `assessment_run`
  - `assessment_result`
  - `valuation_run`
  - `prediction_ledger`
  - `model_release`
- [ ] Add schema/read models for:
  - original vs overridden result blocks
  - visibility state
  - incident state
  - audit export manifest metadata

### Task 2: Override Workflow

**Files:**
- Create: `python/landintel/review/overrides.py`
- Modify: `services/api/app/routes/assessments.py`
- Modify: `python/landintel/services/assessments_readback.py`

- [ ] Implement override creation with strict categories:
  - valuation basis correction
  - valuation assumption set override selection
  - reviewer case disposition note
  - ranking suppression / display block reason
- [ ] Preserve original outputs and add active-override projection on readback.
- [ ] Enforce role gating:
  - analyst: allowed valuation overrides only
  - reviewer: review/disposition actions
  - admin: visibility/release control
- [ ] Audit every override and supersession.

### Task 3: Visibility Gates, Kill Switches, And Incidents

**Files:**
- Create: `python/landintel/review/visibility.py`
- Modify: `services/api/app/routes/admin.py`
- Modify: `services/api/app/routes/assessments.py`
- Modify: `services/api/app/routes/opportunities.py`
- Modify: `python/landintel/services/assessments_readback.py`
- Modify: `python/landintel/services/opportunities_readback.py`
- Modify: `python/landintel/services/model_releases_readback.py`

- [ ] Resolve speaking visibility only through `model_release` + `active_release_scope` + Phase 8A gate state.
- [ ] Implement scope gating rules:
  - default `HIDDEN_ONLY`
  - reviewer/admin visible only when explicit scope enablement exists
  - immediate block when incident/kill-switch is active, replay fails, or hashes are invalid
- [ ] Add kill-switch actions and rollback-safe release visibility changes.
- [ ] Keep opportunity and assessment readback safely redacted for non-privileged contexts.

### Task 4: Health Readback And Audit Export

**Files:**
- Create: `python/landintel/review/audit_export.py`
- Modify: `python/landintel/monitoring/health.py`
- Modify: `services/api/app/routes/admin.py`
- Modify: `services/api/app/routes/assessments.py`
- Modify: `python/landintel/jobs/service.py`
- Create: `services/worker/app/jobs/health.py`
- Modify: `services/worker/app/jobs/connectors.py`

- [ ] Extend `/api/health/data` with:
  - source freshness by family/borough
  - connector failure rate
  - listing parse success rate
  - geometry-confidence distribution
  - extant-permission unresolved rate
  - borough baseline coverage
- [ ] Extend `/api/health/model` with:
  - calibration by band
  - Brier score
  - log loss
  - manual-review agreement by band
  - false-positive reviewer rate
  - abstain rate
  - OOD rate
  - template-level performance
  - economic-health summary
- [ ] Implement audit-export manifest endpoint for a frozen assessment.
- [ ] Add minimal refresh job hooks where asynchronous propagation is useful.

### Task 5: Web Controls And Admin Surfaces

**Files:**
- Create: `services/web/components/assessment-override-panel.tsx`
- Modify: `services/web/app/assessments/[assessmentId]/page.tsx`
- Modify: `services/web/app/review-queue/page.tsx`
- Modify: `services/web/app/admin/health/page.tsx`
- Modify: `services/web/app/admin/model-releases/page.tsx`
- Modify: `services/web/lib/landintel-api.ts`

- [ ] Add override panel and original-vs-overridden result display on assessment detail.
- [ ] Show visibility state badges:
  - hidden
  - visible reviewer-only
  - blocked
- [ ] Add audit export action on assessment view.
- [ ] Polish review queue for manual-review, blocked, and recently changed cases.
- [ ] Turn admin health into usable data/model/economic health panels.
- [ ] Show scope visibility state and incident state in model-release admin.

### Task 6: Tests And Docs

**Files:**
- Create: `tests/test_controls_phase8a.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] Add unit tests for:
  - override preservation of original result
  - role gating
  - redaction logic
  - kill switch behavior
  - rollback behavior
  - health aggregation
  - audit export manifest contents
- [ ] Add integration tests for:
  - assessment override round-trip
  - reviewer/admin visibility gating
  - blocked scope redaction
  - visible scope activation/deactivation
  - audit export endpoint
  - review queue blocked/manual-review surfacing
- [ ] Keep replay-sensitive tests intact so overrides do not corrupt frozen history.
- [ ] Update docs to reflect:
  - hidden vs visible gating
  - override categories and role permissions
  - kill-switch semantics
  - audit export contents
  - remaining operational/manual signoff after code completion

## Spec Coverage Check

- Phase 8 deliverables covered:
  - overrides UI/workflow
  - data/model/economic health summaries
  - kill switches and incidents
  - audit exports
  - controlled visible release gating
- Hard rules preserved:
  - visible OFF by default
  - original frozen artifacts remain immutable
  - release resolution only via release tables/scopes
  - economics remain subordinate to planning state
  - no broader visible rollout claimed from fixture data

