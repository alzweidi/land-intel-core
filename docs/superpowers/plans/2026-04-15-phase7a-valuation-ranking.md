# Phase 7A Valuation and Ranking Implementation Plan

> **For agentic workers:** keep scope limited to Phase 7A valuation and planning-first opportunity ranking. Do not start Phase 8 overrides control plane, dashboards, kill switches, or broader visible-probability rollout.

**Goal:** extend frozen hidden-mode assessments with versioned valuation assumptions, residual land value outputs, market sense-check logic, and planning-first opportunity ranking while keeping hidden probability internal-only.

**Architecture:** build valuation on top of the existing Phase 6A assessment/result/ledger flow so every valuation run is immutable, replayable, and tied to a frozen assessment plus a versioned assumptions set. Ranking remains a deterministic read model that bands by planning state first and only uses economics as a tie-breaker inside each band.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Postgres/PostGIS, existing storage abstraction, Next.js.

---

## Scope

- Add the minimal Phase 7A schema for valuation assumptions, valuation runs/results, and fixture-scale market evidence with provenance.
- Implement fixture-backed HMLR Price Paid + UKHPI bootstrap, plus optional supplementary market benchmarks where useful locally.
- Implement residual valuation, market sense-checks, valuation quality, and immutable valuation integration into frozen assessments.
- Add deterministic planning-first opportunity ranking endpoints and internal UI.
- Extend tests/docs/monitoring hooks without broadening into Phase 8 controls or dashboards.

## Assumptions

- Hidden scoring stays internal-only; standard reads still must not become a visible-probability rollout.
- Fixture-scale London market data is only intended to make Phase 7A honest locally, not to mimic full production coverage.
- Where acquisition basis is missing, Phase 7A must still return post-permission value ranges while keeping uplift and expected uplift null.
- Where a template has no active hidden release, opportunity ranking must keep the case in `HOLD` or equivalent non-speaking rank-only state with an explicit reason.

## Work Plan

1. Add Phase 7A schema/models/enums for valuation assumptions, valuation runs/results, and minimal fixture-backed market evidence tables.
2. Implement valuation bootstrap, UKHPI rebasing, residual method, market sense-checks, valuation quality, and replay-stable payload hashing.
3. Extend assessment execution/readback so frozen assessments include valuation blocks when inputs support them.
4. Implement planning-first opportunity ranking endpoints and internal UI surfaces for opportunities and valuation-aware assessment detail.
5. Add Phase 7A tests, monitoring hooks, and README/AGENTS updates, then rerun backend/frontend/migration checks.
