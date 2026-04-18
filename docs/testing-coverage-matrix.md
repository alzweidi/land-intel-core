# Test and CI/CD hardening coverage matrix

## Final run summary

- Backend command:
  - `ruff check . && pytest --cov=landintel --cov=services --cov-branch --cov-report=xml --cov-report=html`
- Backend result:
  - `324 passed, 25 warnings in 407.98s (0:06:47)`
  - `Total coverage: 100.00%`
- Frontend command:
  - `cd services/web && npm run lint && npm run typecheck && npm run build && npm run test:coverage`
- Frontend result:
  - `32 passed`
  - enforced web critical-surface coverage `100%` lines/statements, `100%` branches, `100%` functions
- Backend artifacts:
  - `artifacts/backend-ci-latest.log`
  - `coverage.xml`
  - `htmlcov/index.html`
- Frontend artifacts:
  - `artifacts/frontend-ci-latest.log`
  - `services/web/coverage/lcov.info`
  - `services/web/coverage/lcov-report/index.html`

## Newly added tests

| Test file | Scope |
| --- | --- |
| `tests/test_platform_hardening.py` | Storage adapters, bootstrap CLIs, API health/admin/auth boundaries, scheduler tick behavior, worker dispatch/claim/retry loops, and job deduplication. |
| `tests/test_assessment_valuation_tail_phase8a.py` | Assessment/valuation helper and validation branches, replay verification, stable payload serialization, and comparable ordering. |
| `tests/test_planning_review_scenarios_tail_phase8a.py` | Historical labels, extant-permission decisions, visibility gating, overrides, and audit-export branch coverage. |
| `tests/test_geometry_listings_monitoring_tail_phase8a.py` | Geometry normalization, title linkage, listing clustering/parsing, scheduler/worker runtime wiring, and monitoring summaries. |
| `tests/test_sites_opportunities_tail_phase8a.py` | Site/readback tails, opportunity redaction and hold behavior, and route-level site list/detail assertions. |
| `tests/test_planning_historical_tail_phase8a.py` | Historical-label rebuild/review helpers, extant-permission helper branches, audit-export failure/minimal manifest paths, and readback shim coverage. |
| `tests/test_runtime_route_tail_phase8a.py` | Session token edge cases, public-page connector dedupe/failure behavior, route 404 translation tails, and scheduler/worker `__main__` execution paths. |
| `tests/test_sites_service_tail_phase8a.py` | Site service geometry/source-link branches and site-readback citation checks. |
| `tests/test_valuation_opportunities_tail_phase8a.py` | Valuation-service ready/failure branches and opportunity list/detail filter coverage. |
| `tests/test_scenarios_tail_phase8a.py` | Scenario suggestion/normalization persistence, headline recompute, and stale-marking branches. |
| `tests/test_review_admin_tail_phase8a.py` | Admin route tails, scope incidents, reviewer-visible transitions, and override serialization edges. |
| `tests/test_sites_tail_wave3_phase8a.py` | Site geometry derivation/update paths, stale-on-geometry-change behavior, and readback rulepack citation checks. |
| `tests/test_assessments_tail_wave3_phase8a.py` | Assessment hidden-release execution-status branches, replay verification, filtered assessment readback, and comparable filtering caps. |
| `tests/test_scenarios_features_tail_wave3_phase8a.py` | Scenario auto-confirm/load/edit helpers and feature designation/archetype helper coverage. |
| `tests/test_monitoring_listing_tail_wave3_phase8a.py` | Monitoring health edge branches, import-common persistence/reuse branches, and listing-service persistence compliance behavior. |
| `tests/test_backend_tail_wave4_phase8a.py` | Tail coverage for auth/session, public-page dedupe, assessment/scenario list routes, valuation basis fallback, and runtime main guards. |
| `tests/test_dense_service_tail_wave5_phase8a.py` | Remaining helper/fallback branches in historical labels, extant permission, site helpers, and assessment replay verification. |
| `tests/test_parsing_tail_wave4_phase8a.py` | HTML/CSV parsing edge cases, JSON-LD fallbacks, document discovery dedupe, and price/date/address extraction tails. |
| `tests/test_evidence_tail_wave4_phase8a.py` | Site/scenario evidence assembly branches, coverage-gap handling, brownfield/policy/constraint polarity, and dedupe helpers. |
| `tests/test_feature_build_tail_wave4_phase8a.py` | Feature/build historical-support, designation profile, archetype-key, snapshot, and nearby-application helper branches. |
| `tests/test_visibility_import_tail_wave4_phase8a.py` | Visibility-mode transitions/incidents, import-common upsert creation paths, and monitoring health warning/metric aggregation branches. |
| `tests/test_geometry_listings_monitoring_tail_wave6_phase8a.py` | Final geometry/listings/monitoring/parser branch tails and worker/runtime tails. |
| `tests/test_worker_jobs_tail_wave6_phase8a.py` | Final job-service and worker-loop orchestration branch tails. |
| `tests/test_planning_review_scoring_readback_tail_wave6_phase8a.py` | Final planning/import, override, scoring-release, and readback branch tails. |
| `tests/test_scenarios_assessments_evidence_features_tail_wave6_phase8a.py` | Final assessments/scenarios/features/evidence tail branches, including non-binary historical-label handling. |
| `tests/test_valuation_sites_tail_wave6_phase8a.py` | Final valuation-market/residual and site-refresh branch tails. |
| `services/web/lib/__tests__/landintel-api.test.ts` | Client request shaping, auth header propagation, and HTTP error handling for the web API client. |
| `services/web/lib/auth/__tests__/session.test.ts` | Header/cookie/session parsing and privileged-role detection. |
| `services/web/components/__tests__/assessment-run-builder.test.tsx` | Assessment creation form validation and submit path behavior. |
| `services/web/components/__tests__/site-scenario-editor.test.tsx` | Scenario refresh/select/edit flow with deterministic mocked API data. |
| `services/web/app/assessments/__tests__/page.test.tsx` | Route-level rendering for the assessments page, including privileged reviewer actions. |

## Backend coverage matrix

| File set | Coverage | Uncovered lines | Uncovered branches | Why any uncovered remains |
| --- | --- | --- | --- | --- |
| `python/landintel/**` and `services/**` under the backend coverage gate | `100.00%` | None | None | None |

## Frontend enforced-scope matrix

| File | Lines | Branches | Funcs | Uncovered lines | Why any uncovered remains |
| --- | --- | --- | --- | --- | --- |
| `services/web/app/assessments/page.tsx` | `100.0%` | `100.0%` | `100.0%` | None | None |
| `services/web/components/assessment-run-builder.tsx` | `100.0%` | `100.0%` | `100.0%` | None | None |
| `services/web/components/site-scenario-editor.tsx` | `100.0%` | `100.0%` | `100.0%` | None | None |
| `services/web/lib/auth/session.ts` | `100.0%` | `100.0%` | `100.0%` | None | None |

## Frontend tests outside the current enforced coverage scope

| File | Test file | Note |
| --- | --- | --- |
| `services/web/lib/landintel-api.ts` | `services/web/lib/__tests__/landintel-api.test.ts` | Covered by assertions in this pass but still outside the enforced Vitest coverage include-list. |

## Replay and immutability validation

- Hidden reviewer assertions run only after `replay_verify_all_assessments(...)`, matching the replay gate before hidden output exposure.
- Assessment tests assert frozen artifacts, stable hash replay, and override preservation of original versus effective state.
- Confirmed-scenario and geometry-change tests assert stale marking after geometry revisions, preserving the Phase 8A immutability rules.
- Valuation tests assert immutable assumption-version behavior and preserve original versus effective override semantics.

## Documented exclusions / rationale

- `python/landintel/assessments/service.py` includes a branch-only exclusion on the `ABSTAIN` guard because earlier guards make the `PASS` false-path unreachable; the code comment documents that rationale inline with `# pragma: no branch`.
