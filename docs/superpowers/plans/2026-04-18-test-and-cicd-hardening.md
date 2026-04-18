# Test and CI/CD Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, high-signal backend and frontend tests plus merge-blocking CI gates for the existing Phase 8A Python + Next.js system without changing runtime architecture or product scope.

**Architecture:** Keep the current FastAPI, worker, scheduler, shared Python package, and Next.js analyst UI intact. Expand test coverage through fixture-driven unit/integration tests, injectable boundaries around environment-dependent code, and GitHub Actions jobs that enforce lint, typecheck, build, and coverage thresholds.

**Tech Stack:** Pytest, pytest-cov, FastAPI TestClient, SQLite-backed fixtures, Vitest, Testing Library, jsdom, Next.js App Router, GitHub Actions.

---

## Scope and constraints

- Stay inside Phase 8A boundaries from `AGENTS.md`.
- Do not add services or infrastructure.
- Prefer deterministic fixtures over network access.
- Mock only external boundaries, never core business decisions.
- Preserve current behavior; only add or tighten tests, tooling, and docs.
- Treat any remaining untestable code path as exceptional and document it inline plus in the final coverage matrix.

## Expected touch points

- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `.github/workflows/ci.yml`
- Modify: `services/web/package.json`
- Create: `services/web/vitest.config.ts`
- Create: `services/web/vitest.setup.ts`
- Create: `services/web/tsconfig.vitest.json`
- Create or extend: `tests/test_worker_scheduler.py`
- Create or extend: `tests/test_api_routes_hardening.py`
- Create or extend: `tests/test_connectors_hardening.py`
- Create or extend: `tests/test_listings_hardening.py`
- Create or extend: `tests/test_sites_hardening.py`
- Create or extend: `tests/test_planning_hardening.py`
- Create or extend: `tests/test_scenarios_hardening.py`
- Create or extend: `tests/test_assessments_hardening.py`
- Create or extend: `tests/test_features_scoring_hardening.py`
- Create or extend: `tests/test_valuation_review_hardening.py`
- Create: `tests/coverage_matrix.md`
- Create or extend: `services/web/lib/__tests__/landintel-api.test.ts`
- Create or extend: `services/web/lib/auth/__tests__/session.test.ts`
- Create or extend: `services/web/components/__tests__/assessment-run-builder.test.tsx`
- Create or extend: `services/web/components/__tests__/site-scenario-editor.test.tsx`
- Create or extend: `services/web/app/**/__tests__/*` for route-level render coverage where feasible

## Phase 1: Baseline inventory

**Files:**
- Inspect: `pyproject.toml`
- Inspect: `services/web/package.json`
- Inspect: `tests/conftest.py`
- Inspect: `services/api/app/routes/*`
- Inspect: `services/worker/app/main.py`
- Inspect: `services/worker/app/jobs/*`
- Inspect: `services/scheduler/app/main.py`
- Inspect: `python/landintel/{connectors,listings,sites,planning,scenarios,assessments,features,scoring,valuation,review,evidence}/*`

- [ ] Record the current backend command surface:
  - `ruff check .`
  - `pytest`
  - `pytest --cov=landintel --cov=services --cov-branch --cov-report=term-missing`
- [ ] Record the current frontend command surface:
  - `cd services/web && npm run lint`
  - `cd services/web && npm run typecheck`
  - `cd services/web && npm run build`
- [ ] Classify modules into:
  - critical path: API routes, worker claim/retry loop, scheduler enqueue rules, assessment/scenario/visibility/valuation/replay services, auth/session boundaries, API client adapters
  - important path: parsing helpers, explanation/quality helpers, rendering components, admin readbacks
  - difficult/unreachable: process-entrypoint infinite loops, metrics startup wrappers, framework-generated shims
- [ ] Save uncovered-line inventory and planned coverage owners into `tests/coverage_matrix.md`.

## Phase 2: Backend gap-closure tests

**Files:**
- Modify or create: `tests/test_worker_scheduler.py`
- Modify or create: `tests/test_api_routes_hardening.py`
- Modify or create: `tests/test_connectors_hardening.py`
- Modify or create: `tests/test_listings_hardening.py`
- Modify or create: `tests/test_sites_hardening.py`
- Modify or create: `tests/test_planning_hardening.py`
- Modify or create: `tests/test_scenarios_hardening.py`
- Modify or create: `tests/test_assessments_hardening.py`
- Modify or create: `tests/test_features_scoring_hardening.py`
- Modify or create: `tests/test_valuation_review_hardening.py`

- [ ] Cover API route success and failure branches:
  - 404 and 422 branches for `services/api/app/routes/{listings,sites,scenarios,assessments,admin,opportunities}.py`
  - auth and reviewer/admin gating via signed session headers
  - hidden-mode visibility behavior for analyst vs reviewer/admin callers
- [ ] Cover worker and scheduler behavior:
  - `process_next_job()` no-job path, success path, dispatch failure path, retry/fail path
  - heartbeat refresh stop behavior using patched refresh results
  - `scheduler_tick()` eligibility, interval skip, queued-source skip, and compliant-source-only enqueue behavior
- [ ] Cover connector and listing invariants:
  - compliant automated source enforcement
  - immutable raw asset / snapshot creation expectations
  - parsing fallbacks, document extraction metadata, clustering determinism
- [ ] Cover site, planning, scenario, assessment, scoring, valuation, and review invariants:
  - geometry revision history and stale-scenario detection
  - scenario confirm/reject behavior and blocked/manual-review branches
  - assessment freeze preconditions, replay-safe readback, comparable fallback determinism
  - hidden release gating, override preservation of original vs effective state
  - valuation assumption versioning, quality downgrades, missing acquisition-basis branches
  - audit export and visibility incident blocking paths

## Phase 3: Frontend tests

**Files:**
- Modify: `services/web/package.json`
- Create: `services/web/vitest.config.ts`
- Create: `services/web/vitest.setup.ts`
- Create: `services/web/tsconfig.vitest.json`
- Create or modify: `services/web/lib/__tests__/landintel-api.test.ts`
- Create or modify: `services/web/lib/auth/__tests__/session.test.ts`
- Create or modify: `services/web/components/__tests__/assessment-run-builder.test.tsx`
- Create or modify: `services/web/components/__tests__/site-scenario-editor.test.tsx`
- Create route-level tests under `services/web/app/**/__tests__/`

- [ ] Add a real web test runner:
  - `vitest`
  - `@testing-library/react`
  - `@testing-library/jest-dom`
  - `jsdom`
- [ ] Cover API client behavior in `services/web/lib/landintel-api.ts`:
  - base URL resolution
  - timeout/error handling
  - payload normalization
  - local fixture fallback behavior where present
- [ ] Cover auth/session behavior:
  - token encode/decode
  - bad signature, bad role, expired session, redirect sanitization
- [ ] Cover core UI business components:
  - `assessment-run-builder` submit success/failure and router navigation
  - `site-scenario-editor` suggest, detail load, confirm, reject, message state, and disabled-state transitions
- [ ] Add at least one route-level render test for a page that exercises the read path with mocked API dependencies.

## Phase 4: Coverage hardening

**Files:**
- Modify: `pyproject.toml`
- Modify: backend modules only if an inline `# pragma: no cover` rationale is truly necessary
- Modify: `tests/coverage_matrix.md`

- [ ] Raise backend coverage gating from `80` to the highest achievable enforced threshold after gap closure.
- [ ] Add frontend coverage thresholds for statements, lines, functions, and branches.
- [ ] Run coverage reports until each uncovered backend/frontend line is either covered or explicitly justified.
- [ ] Document every remaining exclusion in both code and `tests/coverage_matrix.md`.

## Phase 5: GitHub Actions CI/CD

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] Add `backend` job:
  - Python 3.12
  - `pip install -e ".[dev]"`
  - `ruff check .`
  - `pytest --cov=landintel --cov=services --cov-branch --cov-report=xml --cov-report=html --cov-fail-under=<final-threshold>`
  - upload `coverage.xml` and `htmlcov/`
- [ ] Add `frontend` job:
  - Node install with `npm ci`
  - `npm run lint`
  - `npm run typecheck`
  - `npm run build`
  - `npm run test:coverage`
  - upload frontend coverage artifacts
- [ ] Keep jobs merge-blocking via non-zero exit on any failed gate.
- [ ] If an e2e smoke path is practical with existing deterministic fixtures, add it as a dependent job; otherwise document why it remains out of scope for this pass.

## Phase 6: Documentation and evidence

**Files:**
- Modify: `README.md`
- Modify: `tests/coverage_matrix.md`

- [ ] Update the checks section with exact local commands for backend, frontend, and CI parity.
- [ ] Document where backend and frontend coverage artifacts are written.
- [ ] Summarize remaining risks, exclusions, and remediation items.
- [ ] Capture final command outputs for:
  - `ruff check .`
  - backend pytest + coverage
  - frontend lint, typecheck, build, tests with coverage

## Exit criteria

- Backend and frontend tests cover core Phase 8A behavior with deterministic assertions.
- CI runs backend and frontend quality gates on `push` and `pull_request`.
- Coverage thresholds are enforced and evidence is available in generated artifacts.
- Any uncovered code is explicitly justified and traceable in `tests/coverage_matrix.md`.

## 2026-04-18 Scope Escalation: 100% Coverage Push

- Goal expanded from raising baseline coverage gates to eliminating the remaining uncovered backend and frontend lines where feasible within Phase 8A.
- Execution mode for this escalation: parallel worker swarms across independent domains, coordinated by Claude Flow and Codex subagents.
- Priority order:
  1. Frontend enforced-scope coverage to 100%.
  2. Backend low-coverage orchestration modules (`services/worker/app/jobs/*`, `services/api/app/routes/*`, scheduler/worker entrypoints, auth/session, bootstrap CLIs).
  3. Core domain modules with remaining branch gaps (`assessments`, `review`, `services/readback`, `sites`, `valuation`, `planning`, `listings`, `scenarios`, `features`, `evidence`).
  4. CI hardening so coverage gates fail on any regression and artifacts remain inspectable.
- Non-goals remain unchanged from AGENTS.md: no Phase 8B+ scope, no new infrastructure, no network-dependent tests, no behavior reduction.

## 2026-04-18 Coverage escalation wave 2

- Baseline entering this wave: backend coverage `93.27%`, frontend enforced scope `100%`.
- Objective of this wave: continue backend-only coverage closure toward `100%` without expanding Phase 8A scope.
- Execution lanes:
  1. `assessments + valuation + comparables` service logic and tail branches.
  2. `sites + opportunities + readback shim` service/readback branches.
  3. `planning + review + scenario normalization/suggest` branch closure with deterministic fixtures.
  4. `geometry + listings + monitoring + scheduler/worker tail` low-line/high-branch cleanup.
- Rules for this wave:
  - prefer new deterministic tests over production edits;
  - only change production code if a test demonstrates incorrect current behavior;
  - keep each lane in a dedicated test file to avoid merge conflicts;
  - rerun the full backend gate only after the lane files are green in isolation.

## 2026-04-18 Coverage escalation wave 3

- Baseline entering this wave: backend coverage `98.96%` with only branch-tail and a few line-tail misses remaining.
- Objective of this wave: close the final backend tails to `100%` with high-signal tests that prove the underlying logic rather than padding coverage.
- Claude Flow swarm: `swarm-1776529881464-v5edv7` using the maximum tool-supported size of `50` agents under a hierarchical-mesh topology.
- Execution lanes:
  1. `geometry + listings + monitoring + worker` tail branches and defensive line paths.
  2. `planning + review + scoring + readback` remaining branch tails.
  3. `scenarios + assessments + evidence + jobs` remaining branch tails.
  4. `valuation + sites + market/residual` remaining branch tails.
- Acceptance rule for this wave:
  - every new test must correspond to a real branch or invariant named in the coverage report;
  - if a test reveals a production defect, fix the defect and keep the regression test;
  - end only after a fresh full backend coverage run confirms the actual result.
