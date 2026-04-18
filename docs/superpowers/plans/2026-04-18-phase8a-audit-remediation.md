# Phase 8A Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the audited Phase 8A blockers without widening scope beyond scenario gating, point-in-time extant screening, frozen replay/valuation integrity, rulepack citation provenance, and replay-verification truthfulness.

**Architecture:** Keep the existing Phase 8A data model intact. Fix the audited defects by tightening service branching, passing `as_of_date` through extant-permission helpers, using frozen feature and ledger values instead of live mutable scenario state for replay-sensitive paths, and adding acceptance-focused regression tests plus bounded fixture metadata updates.

**Tech Stack:** FastAPI, SQLAlchemy ORM, pytest, JSON fixture baseline packs

---

## Assumptions

- Use the existing `AssessmentFeatureSnapshot` and `PredictionLedger` as the frozen source of truth; do not widen the schema unless a hard blocker appears.
- Keep all changes inside the cited Phase 8A services, readback helpers, and test/fixture files.
- Hidden visibility continues to require explicit replay verification before exposing hidden probability output.

## Tasks

- [ ] `python/landintel/scenarios/normalize.py`: treat extant `ABSTAIN` as review-required, and supersede instead of mutating scenarios that already anchor assessment runs.
- [ ] `python/landintel/planning/extant_permission.py`: add `as_of_date` support and thread it through active/inactive permission and brownfield checks.
- [ ] `python/landintel/assessments/service.py`, `python/landintel/valuation/service.py`, `python/landintel/review/visibility.py`, `python/landintel/domain/models.py`: freeze replay and valuation payload hashing against mutable scenario state and separate hash capture from replay verification.
- [ ] `python/landintel/scenarios/suggest.py`, `python/landintel/services/sites_readback.py`, `python/landintel/evidence/assemble.py`, `tests/fixtures/planning/baseline_packs.json`: require auditable rulepack citations and preserve citation URL/source lookup.
- [ ] `tests/test_scenarios_phase4a.py`, `tests/test_planning_phase3a.py`, `tests/test_assessments_phase5a.py`, `tests/test_scoring_phase6a.py`, `tests/test_valuation_phase7a.py`: add or adjust regression checks for each audit acceptance scenario.

## Audit acceptance mapping

- [ ] Scenario confirmation with missing mandatory coverage or contradictory extant evidence stays review-required and does not become clean `ANALYST_CONFIRMED`.
- [ ] The same frozen assessment inputs rebuilt across different wall-clock dates keep identical extant eligibility, evidence, valuation decision, feature hash, and payload hash.
- [ ] Reconfirming a geometry-changed scenario after an assessment creates a superseding scenario row and does not break old assessment replay.
- [ ] Rulepacks without durable provenance metadata remain blocked.
- [ ] New ledgers start as hash-captured only and move to `VERIFIED` only after explicit replay verification.
