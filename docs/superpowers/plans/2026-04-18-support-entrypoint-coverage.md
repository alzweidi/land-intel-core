# Support and Entrypoint Coverage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic tests for the remaining support and entrypoint branches in the owned slice without changing runtime behavior.

**Architecture:** Keep the work test-only. Extend the existing phase 8A support and hardening tests where practical, and use direct module-level calls for guard/helper branches that are otherwise hard to reach through the HTTP layer.

**Tech Stack:** Pytest, FastAPI test client, existing auth/session fixtures, `monkeypatch`, and small in-memory stubs.

---

### Task 1: Cover API dependency and entrypoint guard branches

**Files:**
- Modify: `tests/test_platform_hardening.py`

- [ ] **Step 1: Add direct branch tests**

Exercise `require_reviewer_actor`, `require_admin_actor`, `database_ready`, scheduler `_coerce_utc`, the scheduler interval skip branch, and the Alembic migration branch in `lifespan`.

- [ ] **Step 2: Run the targeted hardening tests**

Run:
`pytest tests/test_platform_hardening.py -k 'dependency or api_main or scheduler or database_ready' --no-cov`

Expected: the new tests pass without changing behavior.

### Task 2: Cover connector page-capture and manual URL connector branches

**Files:**
- Modify: `tests/test_support_modules_phase8a.py`

- [ ] **Step 1: Add deterministic connector tests**

Exercise `capture_listing_page` with and without document links and `ManualUrlConnector.run` for both parsed and partial outcomes.

- [ ] **Step 2: Run the targeted connector tests**

Run:
`pytest tests/test_support_modules_phase8a.py -k 'manual_url_connector or capture_listing_page' --no-cov`

Expected: the new tests pass without changing behavior.

### Task 3: Verify remaining health coverage with existing deterministic tests

**Files:**
- None

- [ ] **Step 1: Run the existing health-focused tests**

Run:
`pytest tests/test_planning_phase3a.py::test_data_health_exposes_coverage_and_baseline_pack tests/test_controls_phase8a.py::test_health_review_queue_and_audit_export_payloads --no-cov`

Expected: the existing health coverage remains green and continues to exercise the populated health branches.
