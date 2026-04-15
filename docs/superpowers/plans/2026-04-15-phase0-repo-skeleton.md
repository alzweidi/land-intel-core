# Phase 0 Repo Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 0 runnable monorepo skeleton with local dev infrastructure, manual URL snapshot intake, and no business intelligence beyond raw acquisition.

**Architecture:** Use a single shared Python package for settings, schema, queueing, storage, and snapshotting; keep API, worker, and scheduler as thin service entry points. Use Postgres/PostGIS for persistence and a filesystem-or-Supabase storage abstraction so local Docker can mirror the production shape without introducing extra infrastructure.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, APScheduler, Prometheus client, Next.js, TypeScript, Docker Compose, Supabase-compatible auth/storage config.

---

### Task 1: Root Tooling And Docs

**Files:**
- Create: `.env.example`
- Create: `README.md`
- Create: `AGENTS.md`
- Create: `pyproject.toml`
- Create: `docs/superpowers/plans/2026-04-15-phase0-repo-skeleton.md`

- [ ] Define the root Python/tooling config and Phase 0 operating commands.
- [ ] Document the Phase 0 boundary, non-negotiable rules, and exact run/test commands.

### Task 2: Shared Schema And Queue Foundations

**Files:**
- Create: `python/landintel/config.py`
- Create: `python/landintel/domain/enums.py`
- Create: `python/landintel/domain/models.py`
- Create: `python/landintel/db/base.py`
- Create: `python/landintel/db/session.py`
- Create: `db/migrations/env.py`
- Create: `db/migrations/versions/20260415_000001_phase0_bootstrap.py`

- [ ] Implement centralized settings, enums, SQLAlchemy models, and Alembic wiring for the Phase 0 schema.
- [ ] Keep the job queue safe for multiple workers and preserve Supabase-compatible role mapping.

### Task 3: Manual URL Snapshot Flow

**Files:**
- Create: `python/landintel/connectors/base.py`
- Create: `python/landintel/connectors/html_snapshot.py`
- Create: `python/landintel/connectors/manual_url.py`
- Create: `python/landintel/storage/base.py`
- Create: `python/landintel/storage/local.py`
- Create: `python/landintel/storage/supabase.py`
- Create: `python/landintel/jobs/service.py`

- [ ] Implement manual URL queueing, job claiming, HTML fetch isolation, immutable storage, and snapshot persistence.
- [ ] Ensure retries are idempotent at the job level.

### Task 4: Service Entry Points

**Files:**
- Create: `services/api/app/main.py`
- Create: `services/api/app/routes/listings.py`
- Create: `services/api/app/routes/sites.py`
- Create: `services/api/app/routes/scenarios.py`
- Create: `services/api/app/routes/assessments.py`
- Create: `services/api/app/routes/admin.py`
- Create: `services/worker/app/main.py`
- Create: `services/worker/app/jobs/connectors.py`
- Create: `services/scheduler/app/main.py`

- [ ] Add health/readiness endpoints, placeholder later-phase routes, the worker loop, and a bootable scheduler.
- [ ] Keep structured JSON logging and Prometheus-compatible metrics in place from day one.

### Task 5: Frontend, Compose, And Verification

**Files:**
- Create: `services/web/*`
- Create: `docker-compose.yml`
- Create: `infra/compose/docker-compose.vps.yml`
- Create: `tests/test_api.py`
- Create: `tests/test_worker.py`

- [ ] Add the internal web shell with placeholder pages, local Docker runtime, and VPS/Supabase overlay config.
- [ ] Run lint, tests, build, and document any Phase 1 deferrals.
