# Phase 2 Site Geometry Implementation Plan

> **For agentic workers:** keep execution scoped to Phase 2 only. Do not start planning-context enrichment, extant-permission logic, scenarios, assessments, scoring, valuation, or ranking.

**Goal:** turn Phase 1A listing clusters into auditable site candidates with geometry revisions, borough/title linkage, and a basic internal site map/detail workflow.

**Architecture:** build a conservative site layer on top of the existing listings/clusters tables. Canonical geometry is normalized and hashed in EPSG:27700, reference-data imports stay fixture-driven for local/dev, and linkage logic remains deterministic and replayable.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Shapely, PyProj, Postgres-backed jobs, Next.js, MapLibre GL JS.

---

## Scope

- Add Phase 2 schema for sites, geometry revisions, title links, LPA links, market events, and minimal reference tables.
- Add deterministic import/bootstrap paths for London borough boundaries and HMLR title polygon fixtures with immutable provenance.
- Implement cluster-to-site build/refresh, geometry editing, LPA linkage, title linkage, and auditable readback.
- Replace site UI stubs with a basic map/list/detail flow and minimal polygon editor.
- Add Phase 2 tests and docs only.

## Assumptions

- Local/dev reference data uses checked-in fixtures only; no national bulk ingest in this phase.
- If a cluster cannot support a defensible polygon or bbox, the site remains manually reviewable with `POINT_ONLY` or `INSUFFICIENT` rather than being overstated.
- EPSG:4326 is stored only for display/export surfaces; all canonical geometry calculations and hashes use EPSG:27700.

## Work Plan

1. Extend enums, models, migration, and config/runtime dependencies for Phase 2.
2. Implement geometry utilities, reference-data bootstrap, site build/linkage services, and idempotent jobs.
3. Wire API routes, worker dispatch, scheduler-safe job enqueue, and readback serializers.
4. Replace site UI stubs with live site list/detail/map/editor surfaces.
5. Add unit/integration tests, update README/AGENTS, and rerun full checks.
