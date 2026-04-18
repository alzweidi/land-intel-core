# Listings/Sites/Readback/Jobs Service Coverage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic tests for the owned listings, sites, readback, and jobs-service modules so the remaining uncovered branches are exercised without changing runtime behavior.

**Architecture:** Keep the slice test-only. Use real SQLAlchemy sessions where stateful queue behavior matters, and use small in-memory or `SimpleNamespace` stubs for pure parsing and serializer branches. Prefer a small number of focused tests that each close a concrete branch gap over broad integration tests that are harder to reason about.

**Tech Stack:** Pytest, existing `db_session`/`session_factory` fixtures, `monkeypatch`, lightweight stubs, and existing phase fixtures where a real model row is simpler than a mock.

---

### Task 1: Cover queueing, claim, and failure branches in `python/landintel/jobs/service.py`

**Files:**
- Modify: `tests/test_platform_hardening.py` or add `tests/test_jobs_service_phase8a.py`

- [ ] **Step 1: Write the failing tests**

Add deterministic tests for:
- `enqueue_manual_url_job`, `enqueue_csv_import_job`, `enqueue_connector_run_job`
- `enqueue_pld_ingest_job`, `enqueue_borough_register_ingest_job`
- `enqueue_site_planning_enrich_job`, `enqueue_site_extant_permission_recheck_job`
- `enqueue_source_coverage_refresh_job`
- `enqueue_site_scenario_suggest_refresh_job` with and without `template_keys`
- `enqueue_site_scenario_geometry_refresh_job`
- `enqueue_borough_rulepack_scenario_refresh_job`
- `enqueue_scenario_evidence_refresh_job`
- `enqueue_historical_label_rebuild_job`
- `enqueue_assessment_feature_snapshot_build_job`
- `enqueue_comparable_retrieval_build_job`
- `enqueue_replay_verification_batch_job`
- `enqueue_gold_set_refresh_job`
- `enqueue_valuation_data_refresh_job`
- `enqueue_valuation_run_build_job`
- `enqueue_cluster_rebuild_job` returning an existing queued row
- `_deduplicated_job` reusing an existing queued row and creating a new row when the dedupe key is absent
- `claim_next_job` on the PostgreSQL `skip_locked` branch using a fake bind dialect name
- `mark_job_failed` for both `FAILED` and `DEAD` outcomes
- `list_jobs` returning rows in descending `created_at` order

- [ ] **Step 2: Run the targeted tests**

Run:
`pytest tests/test_platform_hardening.py -k 'job_service_deduplicates_and_reuses_existing_jobs or claim_next_job or refresh_job_lock or process_next_job' --no-cov`

Add the new jobs-service test file to that command once it exists.

### Task 2: Cover clustering, parsing, and PDF extraction branches in listings modules

**Files:**
- Modify: `tests/test_listings_phase1a.py` or add `tests/test_listings_coverage_phase8a.py`

- [ ] **Step 1: Write the failing tests**

Add deterministic tests for:
- `build_clusters([])` returning an empty list
- `_compare_pair` branches for:
- canonical URL match
- document hash match
- normalized address plus headline similarity and price/coordinate bonuses
- coordinate-only similarity
- no qualifying edge returning `None`
- `discover_document_links` recognizing brochure vs map PDF links and skipping generic markers
- `extract_pdf_text` returning extracted text/page count for a stub document
- `extract_pdf_text` returning `FAILED` for an exception from `fitz.open`
- parser helpers: `normalize_space`, `normalize_url`, `normalize_address`, `_clean_title`, `_is_generic_headline`, `_extract_savills_description`, `_extract_address_from_title`, `build_search_text`, `extract_text_content`, `parse_price`, `detect_price_basis`, `parse_optional_date`, `detect_listing_status`, `detect_listing_type`, `extract_coordinates_from_text`, `extract_coordinates_from_html`, `_load_json_ld`, `parse_csv_rows`, and the `parse_html_listing` query-coordinate fallback path

- [ ] **Step 2: Run the targeted tests**

Run:
`pytest tests/test_listings_phase1a.py --no-cov`

If the new tests live in a separate file, include it in the command.

### Task 3: Cover serializer and site helper branches in readback and site modules

**Files:**
- Modify: `tests/test_sites_phase2.py` or add `tests/test_readback_site_coverage_phase8a.py`

- [ ] **Step 1: Write the failing tests**

Add deterministic tests for:
- `services/readback.py` import/export wiring
- `list_source_snapshots` and `get_source_snapshot`
- `list_listings` and `get_listing` filters returning empty and populated results
- `list_listing_clusters` and `get_listing_cluster`
- `serialize_listing_summary`, `serialize_listing_detail`, `serialize_cluster_summary`, `serialize_cluster_detail`
- `_current_snapshot_for` with and without an explicit `current_snapshot_id`
- `_sorted_members` ordering by last seen then listing id
- `list_sites` and `get_site`
- `serialize_site_summary` and `serialize_site_detail`
- `_serialize_planning_application` with snapshot document JSON and with live application documents
- `_serialize_policy_area`, `_serialize_constraint_feature`, `_serialize_baseline_pack`
- `_source_snapshots_for_listing`, `_flatten_warnings`, `_rulepack_citations_complete`
- `list_site_scenarios`, `get_scenario_detail`, `serialize_site_scenario_summary`, `serialize_site_scenario_detail`
- `_serialize_site_listing` with and without a current listing
- `_current_auction_date`, `_ranking_factors`, `serialize_valuation_result`
- `list_opportunities` and `get_opportunity` branches for no run, hidden valuation redaction, and ranking suppression
- `build_or_refresh_site_from_cluster`, `save_site_geometry_revision`, `refresh_site_lpa_links`, `refresh_site_title_links`, `refresh_site_links_and_status`
- `_build_cluster_hints`, `_derive_cluster_geometry`, `_ensure_geometry_revision`, `_upsert_market_event`, `_site_audit_payload`

- [ ] **Step 2: Run the targeted tests**

Run:
`pytest tests/test_sites_phase2.py tests/test_api.py -k 'site or listing or opportunity or scenario' --no-cov`

Include any new focused test file in the command once it exists.

### Task 4: Verify the owned slice stays behaviorally unchanged

**Files:**
- None

- [ ] **Step 1: Run only the targeted pytest slice**

Run the commands from Tasks 1-3, plus any narrower node ids needed if one branch still misses coverage.

- [ ] **Step 2: Keep implementation test-only**

If a branch is still uncovered after the new tests land, add one more focused test rather than changing production code.
