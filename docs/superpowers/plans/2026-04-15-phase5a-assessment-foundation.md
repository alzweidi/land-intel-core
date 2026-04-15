# Phase 5A Assessment Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add replay-safe historical labels, point-in-time feature snapshots, frozen pre-score assessments, deterministic comparables, and a minimal gold-set review loop without introducing any probability, model training, valuation, or ranking logic.

**Architecture:** extend the current planning/scenario stack with frozen assessment artifacts keyed by confirmed scenario + `as_of_date`, then build deterministic historical labels, feature payloads, evidence items, comparable sets, and ledger rows from only source-governed facts available on or before that date. Keep all outputs auditable and replayable by storing hashes, provenance, missingness, transform versions, and idempotency keys while leaving all model-release and probability fields null or sentinel-valued.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres-backed jobs, Shapely/PyProj, Next.js.

---

## Scope

- Add Phase 5A schema for assessment runs, frozen feature snapshots, comparable sets, evidence items, prediction ledger rows, and the smallest useful gold-set review records.
- Implement deterministic historical label construction and PIT feature building with provenance and anti-leakage rules.
- Implement pre-score assessment creation/readback, deterministic comparable retrieval, and replay checks.
- Add a minimal internal gold-set review/admin surface.
- Update docs/tests only for Phase 5A.

## Assumptions

- Local/dev remains fixture-scale and London-first; historical label/gold-set support will use the current pilot planning fixtures plus small test-only additions where needed.
- `assessment_result` will exist in Phase 5A only as a stable response/result envelope with `estimate_status = NONE`, all probability fields null, and no model execution.
- `model_release_id` and calibration fields in the ledger/result remain null in this phase because no model release exists yet.

## Work Plan

1. Add Phase 5A schema, enums, and migration for assessment artifacts, comparables, evidence items, prediction ledger rows, and minimal gold-set review records.
2. Implement deterministic historical label mapping, PIT feature building, comparable retrieval, and replay-safe hashing/provenance helpers.
3. Wire assessment creation/readback, worker jobs, and frozen evidence/comparable assembly using confirmed scenarios only.
4. Replace assessment/review shells with a working pre-score assessment view and minimal gold-set review surface.
5. Add Phase 5A unit/integration/replay tests, update README/AGENTS, and rerun full backend/frontend/database/live checks.
