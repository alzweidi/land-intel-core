# AGENTS

## Repo Layout

- `services/api`: FastAPI routes for listings, clusters, sites, admin, and future stubs
- `services/worker`: Postgres-backed worker loop with connector, cluster rebuild, and site refresh/linkage jobs
- `services/scheduler`: recurring enqueue loop for approved automated listing sources with explicit intervals
- `services/web`: Next.js analyst UI focused on listings, clusters, and sites
- `python/landintel`: shared config, ORM models, connector framework, listing parsing/clustering, geospatial/site services, storage, and readback
- `db/migrations`: Alembic revisions
- `infra/compose`: local/VPS compose assets
- `docs`: controlling spec and implementation notes

## Run / Build / Test

- Python setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Backend migrations: `alembic upgrade head`
- Reference bootstrap: `python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev`
- API: `uvicorn services.api.app.main:create_app --factory --host 0.0.0.0 --port 8000`
- Worker: `python -m services.worker.app.main`
- Scheduler: `python -m services.scheduler.app.main`
- Web: `cd services/web && npm install && npm run dev`
- Full stack: `docker compose up --build`
- Checks: `ruff check . && pytest && cd services/web && npm run lint && npm run typecheck && npm run build`

## ExecPlan Rule

- For any long multi-step phase, create or update a short execution plan in `docs/superpowers/plans/` before coding.
- Keep the plan scoped to the active phase only, record major assumptions, and update it if implementation boundaries change.
- Do not start a later phase early just because adjacent stubs or folders already exist.

## Non-Negotiable Rules From The Spec

- Stop at Phase 2. Do not start Phase 3 planning context/evidence packs, extant-permission logic, planning-register ingestion, policy-layer ingestion, scenarios, assessments, scoring, valuation, ranking, or model training.
- No AWS, Kubernetes, Redis, vector DB, domain microservices, or separate model-serving service.
- Use the Postgres-backed `job_run` queue with `FOR UPDATE SKIP LOCKED`.
- Every connector run must create one `source_snapshot`, one or more `raw_asset` rows, a coverage note, and a parse status.
- Never overwrite raw assets or listing snapshots in place.
- Automated connectors are blocked unless `listing_source.compliance_mode == COMPLIANT_AUTOMATED`.
- Do not ship portal-specific scrapers without explicit compliance approval.
- Treat listing text as market evidence only, never planning truth.
- Canonical spatial operations run in EPSG:27700 only; EPSG:4326 is for display/export only.
- HMLR INSPIRE title polygons are indicative evidence only, not parcel truth.
- Support multi-title linkage.
- Apply the cross-LPA rule exactly: trivial overlap stays on the majority LPA and flags; material overlap requires manual clipping or confirmation.
- Audit site creation, refresh, and geometry revision events.

## Phase 2 Done Means

- `docker compose up --build` boots `api`, `worker`, `scheduler`, `web`, and local PostGIS
- `alembic upgrade head` succeeds
- Phase 1A listing ingestion and clustering still pass locally
- local/dev borough and title fixtures can be imported through the reference bootstrap path
- a listing cluster can be converted into a `site_candidate` with an auditable geometry revision
- analysts can save new geometry revisions without overwriting prior evidence
- borough assignment and title linkage are visible in API and UI
- the web app renders the site list/detail and MapLibre geometry editor locally
- tests and lint/build checks pass

## Source Approval Notes

- `manual_url` and `csv_import` are seeded safe sources for analyst-triggered intake only.
- automated sources must exist in `listing_source`, be active, and declare `COMPLIANT_AUTOMATED`.
- scheduler refresh only triggers when an approved automated source also sets `refresh_policy_json.interval_hours`.
