# Phase 6A Hidden Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** add a replayable hidden-only planning probability layer with logistic regression, calibration, release registry, OOD/estimate-quality logic, and explanation payloads without introducing visible probability, valuation, or ranking.

**Architecture:** extend the Phase 5A frozen assessment pipeline so model training and scoring operate only on versioned point-in-time feature snapshots and explicit historical labels, then resolve hidden releases exclusively through a release registry with honest per-template readiness states. Keep scoring deterministic and replay-safe by persisting immutable model/calibration artifacts, validation manifests, release resolution metadata, and final ledger payload hashes while preserving all abstain/manual-review guardrails from earlier phases.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, scikit-learn, NumPy, Postgres-backed jobs, Next.js.

---

## Scope

- Audit the current Phase 5 foundations and treat unsupported templates as explicit `NOT_READY` / `INSUFFICIENT_DATA` release states rather than fabricating training success.
- Add the minimal Phase 6A schema for model releases, active release scopes, and scored assessment/result/ledger metadata.
- Implement offline logistic-regression training, calibration, validation manifests, release registration, activation, and rollback.
- Extend assessment execution to resolve hidden releases, compute hidden probabilities when available, and otherwise keep stable pre-score results.
- Add hidden-only explanation output, estimate-quality logic, minimal internal release/admin controls, and hidden-score UI.

## Audit Findings / Assumptions

- Current Phase 5 replayability is honest: tests confirm stable feature hashes and stable pre-score payload hashes for repeated assessment runs.
- Current gold-set coverage is not honest for every enabled template: fixture-scale labels only exist for `resi_5_9_full` today.
- Phase 6A will therefore produce an activatable hidden release only where support is sufficient and will register explicit not-ready states for unsupported templates instead of backfilling larger Phase 5B data work.
- Hidden score remains internal/admin-only in this phase. Standard analyst surfaces stay non-speaking unless explicitly in hidden evaluation context.

## Work Plan

1. Add Phase 6A schema and registry models for model releases, active release scopes, and scored assessment/ledger metadata.
2. Implement offline training, calibration, validation, artifact storage, and honest per-template release registration with not-ready states for insufficient support.
3. Implement OOD, estimate-quality, and explanation generation on top of frozen assessment feature snapshots.
4. Extend assessment execution, admin release controls, and hidden-score UI/readback to resolve active releases and preserve replay-safe ledger writes.
5. Add Phase 6A tests, update README/AGENTS, and rerun backend/frontend/migration checks.
