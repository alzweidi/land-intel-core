# Phase 8A Launch-Readiness Remediation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Keep scope to the automated-refresh readiness blockers only.

**Goal:** Make the repo launch-ready for Phase 8A automated listing refresh by fixing the seeded automated-source interval gap, deduplicating connector-run queueing, replacing fixture-backed source truth with live API/admin data, and aligning the admin CSV surface with the supported file-upload contract.

**Architecture:** Keep the existing Phase 8A data model, queue model, and scheduler selection logic. Fix correctness through one forward Alembic backfill, a small queue-service change, a live source read route, and web/admin read-model cleanup. Do not add new source families, run-history endpoints, or later-phase rollout work.

## Assumptions

- `example_public_page` remains the canonical repo-seeded automated source.
- `/api/admin/jobs` remains the only run-history/count source for the admin console.
- CSV import stays file-upload only in this phase; the web UI must stop advertising pasted CSV text.
- Runtime proof happens in the local compose stack and is a hard gate before commit.

## Tasks

- [ ] Add a forward Alembic migration that backfills `listing_source.refresh_policy_json.interval_hours` for `example_public_page` and adds `payload_json.dedupe_key = "source:<source_name>"` to queued/running `LISTING_SOURCE_RUN` jobs.
- [ ] Patch the original Phase 1A listing-ingestion migration so fresh installs seed `example_public_page` with explicit `interval_hours`.
- [ ] Change connector enqueueing to use the existing deduplicated job helper and preserve current scheduler behavior.
- [ ] Add `GET /api/listings/sources` backed by the existing listings readback service.
- [ ] Replace fixture-backed source metadata on `/listings` and `/admin/source-runs` with live source reads; derive admin run counts from `/api/admin/jobs`; normalize legacy `approved_public_page` inputs to `example_public_page`.
- [ ] Make the admin CSV trigger UI file-upload only so it matches the live API contract.
- [ ] Add or update backend tests for seeded interval exposure, connector dedupe, repeated connector POST behavior, live listing-source reads, and migration backfill behavior.
- [ ] Add a small web helper module for live source/admin-run mapping and put it plus `app/admin/source-runs/page.tsx`, `app/listings/page.tsx`, and `components/listing-run-panel.tsx` under Vitest 100% coverage.
- [ ] Add web tests proving live source pages do not fall back to fixture source metadata, admin run counts come from admin jobs, the connector default resolves to `example_public_page`, legacy key normalization works, and CSV import is file-only.
- [ ] Update operator docs touched by this slice so README/local usage/testing instructions match the verified runtime behavior.

## Verification Gates

- [ ] Run `ruff check .`
- [ ] Run `pytest`
- [ ] Run `cd services/web && npm run lint && npm run typecheck && npm run test:coverage && npm run build`
- [ ] Run `docker compose up --build -d`
- [ ] Run `docker compose exec -T api alembic upgrade head`
- [ ] Run `bash scripts/setup_local.sh`
- [ ] Trigger `POST /api/listings/connectors/example_public_page/run`
- [ ] Verify `/api/listings/sources`, `/api/admin/jobs`, `/api/health/data`, `/api/admin/review-queue`, `/listings`, and `/admin/source-runs`
- [ ] Run `./scripts/smoke_prod.sh` against the local stack with required auth env vars
- [ ] Finish with independent spec and code-quality review before deciding whether to commit
