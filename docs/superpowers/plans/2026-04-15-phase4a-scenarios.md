# Phase 4A Scenario Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add auditable, editable, scenario-conditioned planning hypotheses on top of the existing site and planning context layers without introducing scoring, valuation, or probability output.

**Architecture:** extend the Phase 3A site object with seeded scenario templates, usable cited borough rulepacks, deterministic suggestion heuristics, conservative confirmation state management, and scenario-conditioned evidence readback. Keep all scenario logic replayable from frozen site geometry hashes, source snapshots, and explicit rulepack provenance while leaving assessment and model execution clearly stubbed.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres-backed jobs, Shapely/PyProj, Next.js, MapLibre.

---

## Scope

- Add Phase 4A schema for scenario templates, site scenarios, and review history.
- Upgrade current baseline-pack placeholder rulepacks into machine-readable, cited pilot rulepacks.
- Implement deterministic scenario suggestion, conservative confirmation/edit/reject flows, stale-state handling after geometry changes, and scenario-conditioned evidence.
- Extend scenario/site APIs, worker jobs, and analyst UI for suggest/edit/confirm/reject flows.
- Add tests and docs only for Phase 4A.

## Assumptions

- Pilot borough support remains fixture-scale and uses the already seeded Camden baseline pack plus limited Southwark contrast data where useful.
- “Nearest historical support is strong” cannot yet be satisfied honestly from current implemented data, so auto-confirm must default to `ANALYST_REQUIRED` unless a future evidence source is added.
- Scenario rationale must stay deterministic and cite existing source snapshots, planning links, rulepacks, and site facts only.

## Work Plan

1. Add scenario schema, enums, migration, seeded templates, and cited rulepack fixture upgrades.
2. Implement deterministic suggestion heuristics, scenario normalization/state transitions, stale detection, and scenario-conditioned evidence assembly.
3. Wire scenario API routes, readback, and Postgres-backed jobs for suggestion refresh and evidence refresh.
4. Replace the scenario UI shells with a working editor/compare flow tied to site detail and source-backed rationale.
5. Add Phase 4A unit and integration tests, update README/AGENTS, and rerun backend/frontend/live checks.
