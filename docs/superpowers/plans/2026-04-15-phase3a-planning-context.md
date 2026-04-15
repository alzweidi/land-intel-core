# Phase 3A Planning Context Implementation Plan

> **For agentic workers:** keep execution scoped to Phase 3A only. Do not start scenario suggestion/confirmation, assessment runs, scoring, valuation, ranking, or any visible/hidden probability work.

**Goal:** make site detail useful before ML by adding planning/history ingestion foundations, deterministic site enrichment, extant-permission screening, and auditable evidence assembly.

**Architecture:** extend the existing site layer with fixture-scale planning, policy, constraint, and coverage tables plus deterministic enrichment services. Borough register data remains the authority of record for labels and extant permission where available, PLD stays supplemental, and every conclusion carries coverage/freshness caveats and raw-source provenance.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Shapely, PyProj, Postgres-backed jobs, Next.js, MapLibre GL JS.

---

## Scope

- Add Phase 3A schema for planning applications, policy/constraint features, coverage snapshots, baseline packs, rulepack scaffolding, and evidence-friendly site facts.
- Add fixture/bootstrap ingestion for PLD, borough planning register, brownfield, selected Planning Data constraints, flood, and policy layers with immutable provenance.
- Implement deterministic site planning enrichment, extant-permission screening, and evidence assembly with `FOR`, `AGAINST`, and `UNKNOWN`.
- Extend site APIs, worker jobs, data-health readback, and site detail UI to expose permission state, planning context, raw links, freshness, and gaps.
- Add Phase 3A tests and docs only.

## Assumptions

- Local/dev remains London-only and fixture-scale, centered on one pilot borough plus small cross-borough support samples where needed for joins and gap states.
- Borough baseline packs and rulepacks will exist structurally with provenance and status metadata, but not with full signed-off scenario logic in this phase.
- Missing mandatory coverage must surface as `ABSTAIN` or manual review in the extant-permission result rather than defaulting to a clean negative.

## Work Plan

1. Extend enums, models, migration, and runtime dependencies for Phase 3A planning, policy, coverage, and evidence entities.
2. Implement fixture-scale planning/policy/bootstrap import paths and source-coverage capture with immutable `source_snapshot` and `raw_asset` provenance.
3. Implement site planning enrichment, extant-permission screening, and evidence assembly services plus idempotent jobs.
4. Extend site/detail and health APIs, then wire the site detail UI to permission state, planning context, evidence, and coverage warnings.
5. Add unit/integration/geospatial regression tests, update README/AGENTS, and rerun full checks plus live smoke paths.
