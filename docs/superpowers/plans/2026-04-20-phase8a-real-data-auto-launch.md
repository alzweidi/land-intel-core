# Phase 8A Real Data Auto-Launch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 8A capable of running a truthful internal launch with real automated data refresh, automatic progression from compliant listed-source intake into sites/scenarios/assessments/opportunities, and live operational surfaces that prove the system is working.

**Architecture:** Keep the existing Phase 8A stack and extend it in place. Reuse the Postgres job queue, generic public-page connector, current site/scenario/assessment builders, and live web/admin surfaces. Add remote-refresh support for official datasets, add narrow worker chaining for eligible listing clusters, and keep all visibility/probability controls inside the current hidden/reviewer-gated model.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres job queue, APScheduler, Pydantic settings, Next.js/TypeScript, existing storage abstraction, Docker Compose.

---

## File Structure

- Modify: `python/landintel/config.py`
- Modify: `pyproject.toml`
- Modify: `python/landintel/domain/enums.py`
- Modify: `services/scheduler/app/main.py`
- Modify: `python/landintel/jobs/service.py`
- Modify: `python/landintel/listings/service.py`
- Create: `python/landintel/connectors/tabular_feed.py`
- Modify: `services/worker/app/jobs/connectors.py`
- Modify: `services/worker/app/jobs/site_build.py`
- Modify: `services/worker/app/jobs/scenarios.py`
- Create: `python/landintel/geospatial/official_sources.py`
- Modify: `python/landintel/planning/bootstrap.py`
- Modify: `python/landintel/valuation/bootstrap.py`
- Modify: `python/landintel/geospatial/bootstrap.py`
- Modify: `services/worker/app/jobs/planning_enrich.py`
- Modify: `services/worker/app/jobs/valuation.py`
- Create: `python/landintel/data_fetch/http_assets.py`
- Create: `python/landintel/planning/official_sources.py`
- Create: `python/landintel/valuation/official_sources.py`
- Modify: `db/migrations/versions/20260415_000002_phase1a_listing_ingestion.py`
- Create: `db/migrations/versions/20260420_000012_phase8a_real_source_launch.py`
- Modify: `services/api/app/routes/admin.py`
- Modify: `services/api/app/routes/sites.py`
- Modify: `services/web/lib/landintel-api.ts`
- Modify: `services/web/app/listings/page.tsx`
- Modify: `services/web/app/listing-clusters/page.tsx`
- Modify: `services/web/app/sites/page.tsx`
- Modify: `services/web/app/opportunities/page.tsx`
- Modify: `services/web/app/admin/source-runs/page.tsx`
- Modify: `docs/guides/local-usage.md`
- Modify: `docs/operations/runbook.md`
- Modify: `README.md`
- Test: `tests/test_phase8a_real_data_launch.py`
- Test: `tests/test_phase8a_official_refresh.py`
- Test: `services/web/lib/__tests__/real-data-launch.test.ts`
- Test: `services/web/app/sites/__tests__/page.test.tsx`
- Test: `services/web/app/opportunities/__tests__/page.test.tsx`

## Major Assumptions

- A truthful launch still requires at least one compliant listed source to be configured and live.
- The first truthful real automated listed source for this slice is the Cabinet Office monthly `Surplus Property` feed, delivered as a public OGL XLSX.
- Standard analyst-visible probability remains restricted by existing Phase 8A rules.
- Official/open planning inputs may improve evidence quality while still preserving manual-review or abstain behavior where authority-grade coverage is missing.

### Task 1: Source Configuration And Launch Controls

**Files:**
- Modify: `python/landintel/config.py`
- Modify: `README.md`
- Modify: `docs/guides/local-usage.md`
- Modify: `docs/operations/runbook.md`

- [ ] Add config entries for real-data mode and official-source URLs/manifests.
- [ ] Document the canonical Phase 8A launch distinction:
  - official automated sources
  - compliant automated listed sources
  - fixture fallbacks for local/test
- [ ] Document required operator env/config for running a real automated cycle.
- [ ] Document the honest limit: no compliant listed source means no truthful real opportunity queue.

### Task 2: Official Data Remote Refresh

**Files:**
- Create: `python/landintel/data_fetch/http_assets.py`
- Create: `python/landintel/planning/official_sources.py`
- Create: `python/landintel/valuation/official_sources.py`
- Create: `python/landintel/geospatial/official_sources.py`
- Modify: `python/landintel/planning/bootstrap.py`
- Modify: `python/landintel/valuation/bootstrap.py`
- Modify: `services/worker/app/jobs/planning_enrich.py`
- Modify: `services/worker/app/jobs/valuation.py`

- [ ] Add a small shared HTTP fetch helper that downloads a remote asset, records source metadata, and gives import code a local file handle/bytes payload.
- [ ] Extend valuation refresh to support real remote imports for:
  - HMLR Price Paid
  - UKHPI
- [ ] Extend at least one reference/planning family to support real remote refresh rather than fixture-only import.
- [ ] Keep all existing fixture paths and tests working when remote configuration is absent.
- [ ] Persist job summaries so admin/health surfaces can prove which mode ran and what was imported.

### Task 2B: Real Automated Listed Source Onboarding

**Files:**
- Modify: `pyproject.toml`
- Modify: `python/landintel/domain/enums.py`
- Create: `python/landintel/connectors/tabular_feed.py`
- Modify: `python/landintel/listings/service.py`
- Modify: `db/migrations/versions/20260415_000002_phase1a_listing_ingestion.py`
- Create: `db/migrations/versions/20260420_000012_phase8a_real_source_launch.py`

- [ ] Add a generic automated tabular-feed connector capable of fetching XLSX/CSV source files over HTTPS and emitting immutable listing snapshots.
- [ ] Onboard the Cabinet Office `Surplus Property` feed as the first truthful `COMPLIANT_AUTOMATED` real listed source.
- [ ] Filter the feed to London surplus opportunities that are genuinely on-market or under-offer and map them into land / land-with-building / redevelopment listing types honestly.
- [ ] Make the new real source the operator-facing default for live local/internal bring-up while preserving fixture/test paths.

### Task 3: Queue Automation From Cluster To Opportunity

**Files:**
- Modify: `python/landintel/jobs/service.py`
- Modify: `python/landintel/listings/service.py`
- Modify: `services/worker/app/jobs/connectors.py`
- Modify: `services/worker/app/jobs/site_build.py`
- Modify: `services/worker/app/jobs/scenarios.py`

- [ ] Add a narrow “eligible cluster” predicate based on current listing status and land-like listing type.
- [ ] After cluster rebuild, enqueue `SITE_BUILD_REFRESH` for newly eligible or changed clusters not already represented by an active site build.
- [ ] Make `SITE_BUILD_REFRESH` mirror the manual API flow by enqueueing scenario suggestion after a successful site build.
- [ ] After scenario suggestion, detect current non-stale `AUTO_CONFIRMED` scenarios and auto-build today’s assessment idempotently.
- [ ] Keep `ANALYST_REQUIRED` scenarios in review/manual states rather than force-building assessments.
- [ ] Add replay-safe dedupe and audit coverage so automated re-runs do not create inconsistent site/scenario/assessment state.

### Task 4: Live Web And Admin Readiness

**Files:**
- Modify: `services/api/app/routes/admin.py`
- Modify: `services/api/app/routes/sites.py`
- Modify: `services/web/lib/landintel-api.ts`
- Modify: `services/web/app/listings/page.tsx`
- Modify: `services/web/app/listing-clusters/page.tsx`
- Modify: `services/web/app/sites/page.tsx`
- Modify: `services/web/app/opportunities/page.tsx`
- Modify: `services/web/app/admin/source-runs/page.tsx`

- [ ] Make listings, clusters, sites, opportunities, and source-run/admin surfaces clearly reflect live automated state.
- [ ] Ensure the UI distinguishes:
  - live opportunities
  - hold/manual-review opportunities
  - empty queues caused by absent compliant listed sources
- [ ] Surface enough source/job status to debug whether data is flowing without dropping to the shell.
- [ ] Preserve current hidden/reviewer gating for probability detail.

### Task 5: Tests, Verification, And Runtime Proof

**Files:**
- Create: `tests/test_phase8a_real_data_launch.py`
- Create: `tests/test_phase8a_official_refresh.py`
- Modify/Create: `services/web/lib/__tests__/real-data-launch.test.ts`
- Modify/Create: `services/web/app/sites/__tests__/page.test.tsx`
- Modify/Create: `services/web/app/opportunities/__tests__/page.test.tsx`

- [ ] Add backend coverage for:
  - eligible-cluster auto-promotion
  - site-build -> scenario-suggest chaining
  - auto-assessment creation for `AUTO_CONFIRMED`
  - no auto-assessment for analyst-required cases
  - remote official refresh helper behavior and fixture fallback
- [ ] Add web coverage for live site/opportunity/admin rendering under:
  - populated live queue
  - hold/manual-review queue
  - truthful empty state
- [ ] Run the full verification suite:
  - `ruff check .`
  - `pytest`
  - `cd services/web && npm run lint`
  - `cd services/web && npm run typecheck`
  - `cd services/web && npm run test:coverage`
  - `cd services/web && npm run build`
- [ ] Run live stack proof:
  - `docker compose down -v`
  - `docker compose up --build -d`
  - `docker compose exec -T api alembic upgrade head`
  - `bash scripts/setup_local.sh`
  - trigger a compliant source run
  - verify listings -> clusters -> sites -> opportunities in the UI/API
  - run `./scripts/smoke_prod.sh`

## Spec Coverage Check

- Real automated data refresh: covered by Tasks 1 and 2.
- Automatic progression from listed intake to opportunities: covered by Task 3.
- Live frontend/admin truth surfaces: covered by Task 4.
- 100% coverage and runtime proof: covered by Task 5.
- Phase 8A hard rules preserved:
  - compliant automated sources only
  - no off-market expansion
  - no broad visible probability rollout
  - planning-first opportunity logic remains intact
