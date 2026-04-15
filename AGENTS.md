# AGENTS

## Repo Layout

- `services/api`: FastAPI routes for listings, clusters, admin, and future stubs
- `services/worker`: Postgres-backed worker loop with connector execution and cluster rebuild jobs
- `services/scheduler`: recurring enqueue loop for approved automated listing sources with explicit intervals
- `services/web`: Next.js analyst UI focused on listings and clusters in Phase 1A
- `python/landintel`: shared config, ORM models, connector framework, listing parsing/clustering, storage, and readback
- `db/migrations`: Alembic revisions
- `infra/compose`: local/VPS compose assets
- `docs`: controlling spec and implementation notes

## Run / Build / Test

- Python setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Backend migrations: `alembic upgrade head`
- API: `uvicorn services.api.app.main:create_app --factory --host 0.0.0.0 --port 8000`
- Worker: `python -m services.worker.app.main`
- Scheduler: `python -m services.scheduler.app.main`
- Web: `cd services/web && npm install && npm run dev`
- Full stack: `docker compose up --build`
- Checks: `ruff check . && pytest && cd services/web && npm run lint && npm run typecheck && npm run build`

## Non-Negotiable Rules From The Spec

- Stop at Phase 1A. Do not start site geometry, title linkage, LPA linkage, planning enrichment, extant-permission logic, scenarios, assessments, scoring, valuation, or model training.
- No AWS, Kubernetes, Redis, vector DB, domain microservices, or separate model-serving service.
- Use the Postgres-backed `job_run` queue with `FOR UPDATE SKIP LOCKED`.
- Every connector run must create one `source_snapshot`, one or more `raw_asset` rows, a coverage note, and a parse status.
- Never overwrite raw assets or listing snapshots in place.
- Automated connectors are blocked unless `listing_source.compliance_mode == COMPLIANT_AUTOMATED`.
- Do not ship portal-specific scrapers without explicit compliance approval.
- Treat listing text as market evidence only, never planning truth.
- Keep canonical spatial operations for later EPSG:27700 work, but do not implement spatial business logic in this phase.

## Phase 1A Done Means

- `docker compose up --build` boots `api`, `worker`, `scheduler`, `web`, and local PostGIS
- `alembic upgrade head` succeeds
- the system supports `manual_url`, `csv_import`, and a generic compliant public-page connector
- worker runs create immutable source snapshots, raw assets, listing items, listing snapshots, and listing documents
- duplicate listings cluster deterministically with a rebuild job
- listing list/detail and cluster list/detail APIs work locally
- the web app renders the listing and connector surfaces locally
- tests and lint/build checks pass

## Source Approval Notes

- `manual_url` and `csv_import` are seeded safe sources for analyst-triggered intake only.
- automated sources must exist in `listing_source`, be active, and declare `COMPLIANT_AUTOMATED`.
- scheduler refresh only triggers when an approved automated source also sets `refresh_policy_json.interval_hours`.
