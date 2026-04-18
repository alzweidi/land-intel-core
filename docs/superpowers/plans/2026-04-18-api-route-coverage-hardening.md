# API Route Coverage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add high-signal route tests for the owned API modules so remaining negative, error, and status branches are covered without changing route behavior.

**Architecture:** Keep the work test-only. Use existing client and auth fixtures where the route already depends on request actors, and use monkeypatching only where a branch can only be reached by forcing a service-layer exception or a missing readback result. Prefer one focused test file for shared negative-path coverage rather than scattering one-off assertions across unrelated phase tests.

**Tech Stack:** Pytest, FastAPI test client, existing `tests/conftest.py` fixtures, `monkeypatch`.

---

### Task 1: Cover listings, sites, scenarios, and opportunities negative paths

**Files:**
- Modify: `tests/test_listings_phase1a.py`
- Modify: `tests/test_sites_phase2.py`
- Modify: `tests/test_scenarios_phase4a.py`
- Modify: `tests/test_valuation_phase7a.py` or create a small supporting route-negative test file if it keeps the slice cleaner

- [ ] **Step 1: Write the failing tests**

Add route-level tests for:
- `POST /api/listings/import/csv` empty upload -> `400`
- `GET /api/listings/{listing_id}` missing listing -> `404`
- `GET /api/listing-clusters/{cluster_id}` missing cluster -> `404`
- `GET /api/sites/{site_id}` missing site -> `404`
- `POST /api/sites/{site_id}/geometry` service failure -> `422`
- `POST /api/sites/{site_id}/extant-permission-check` missing site -> `404`
- `POST /api/sites/from-cluster/{cluster_id}` service failure -> `422`
- `GET /api/scenarios/{scenario_id}` missing scenario -> `404`
- `POST /api/scenarios/{scenario_id}/confirm` normalize failure -> `422`
- `POST /api/scenarios/{scenario_id}/confirm` missing readback after commit -> `404`
- `POST /api/sites/{site_id}/scenarios/suggest` generic service failure -> `422`
- `GET /api/opportunities/{site_id}` missing opportunity -> `404`

- [ ] **Step 2: Run the targeted route tests**

Run:
`pytest tests/test_listings_phase1a.py tests/test_sites_phase2.py tests/test_scenarios_phase4a.py tests/test_valuation_phase7a.py -q`

Expected: the new negative-path tests fail before implementation and pass after.

### Task 2: Cover assessments and admin negative paths

**Files:**
- Modify: `tests/test_assessments_phase5a.py`
- Modify: `tests/test_controls_phase8a.py`

- [ ] **Step 1: Write the failing tests**

Add route-level tests for:
- `POST /api/assessments` build failure -> `422`
- `POST /api/assessments` missing detail after create -> `404`
- `GET /api/assessments/{assessment_id}` missing assessment -> `404`
- `POST /api/assessments/{assessment_id}/override` access failure -> `422`
- `POST /api/assessments/{assessment_id}/override` missing detail after override -> `404`
- `GET /api/assessments/{assessment_id}/audit-export` access failure -> `422`
- `GET /api/admin/source-snapshots/{snapshot_id}` missing snapshot -> `404`
- `GET /api/admin/gold-set/cases/{case_id}` missing case -> `404`
- `POST /api/admin/gold-set/cases/{case_id}/review` missing case -> `404`
- `POST /api/admin/model-releases/{release_id}/retire` service failure -> `422`
- `POST /api/admin/release-scopes/{scope_key}/incident` unsupported action -> `422`

- [ ] **Step 2: Run the targeted route tests**

Run:
`pytest tests/test_assessments_phase5a.py tests/test_controls_phase8a.py -q`

Expected: the new negative-path tests fail before implementation and pass after.

### Task 3: Verify the owned route slice is covered

**Files:**
- None

- [ ] **Step 1: Run only the targeted pytest slice**

Run the two commands above, plus any narrower node IDs needed to isolate a failure if one branch still misses coverage.

- [ ] **Step 2: Keep behavior unchanged**

If a route still has an uncovered branch after the new tests land, add one more focused negative-path test rather than changing route code.
