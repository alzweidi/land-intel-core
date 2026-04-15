# AGENTS

## Repo Layout

- `services/api`: FastAPI app and route handlers
- `services/worker`: Postgres-backed worker loop and job executors
- `services/scheduler`: recurring scheduler loop
- `services/web`: Next.js + TypeScript internal shell
- `python/landintel`: shared settings, models, queue, storage, and snapshot modules
- `db/migrations`: Alembic environment and schema revisions
- `infra/compose`: compose overlays and deployment notes
- `docs`: controlling spec and implementation notes

## Run / Build / Test

- Local Python setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Backend migrations: `alembic upgrade head`
- API: `uvicorn services.api.app.main:create_app --factory --host 0.0.0.0 --port 8000`
- Worker: `python -m services.worker.app.main`
- Scheduler: `python -m services.scheduler.app.main`
- Web: `cd services/web && npm install && npm run dev`
- Full local stack: `docker compose up --build`
- Checks: `ruff check . && pytest && cd services/web && npm run lint && npm run build`

## Non-Negotiable Rules From The Spec

- Phase 0 only. Do not start listing enrichment, geometry intelligence, planning intelligence, scoring, valuation, or model training.
- No AWS, Kubernetes, Redis, vector DB, domain microservices, or separate model-serving service.
- Use a Postgres-backed job queue with `FOR UPDATE SKIP LOCKED`.
- Preserve immutable raw snapshots. Never overwrite fetched assets.
- Keep canonical spatial support ready for EPSG:27700 later, but do not implement spatial business logic yet.
- Do not build parcel-only scoring, visible probability logic, or scenario-less planning scores.
- Treat listing text as indicative only; not as planning truth.
- Authorization must remain app-enforced even when Supabase Auth is the identity provider.

## Phase 0 Done Means

- `docker compose up --build` boots `api`, `worker`, `scheduler`, `web`, and local PostGIS
- `alembic upgrade head` succeeds cleanly
- `POST /api/listings/intake/url` queues a job
- the worker stores a raw HTML snapshot plus `source_snapshot` and `raw_asset` metadata
- tests and lint/build checks pass
- README is sufficient for another engineer to run the stack

