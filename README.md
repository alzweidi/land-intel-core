# land-intel-core

Phase 0 monorepo skeleton for the London-first land intelligence platform. The controlling spec is [docs/london_land_intelligence_implementation_spec_v1 (2).md](/Users/atta/land-intel-core/docs/london_land_intelligence_implementation_spec_v1%20(2).md).

## What Phase 0 Includes

- FastAPI API, Python worker, and Python scheduler
- shared `python/landintel` package
- Next.js + TypeScript internal web shell
- Alembic-backed schema for `source_snapshot`, `raw_asset`, `job_run`, `audit_event`, and app-level auth/role tables
- local filesystem storage adapter plus Supabase Storage abstraction
- Docker Compose for local PostGIS-backed development
- env-driven settings for VPS backend + Supabase + Netlify deployments
- manual URL intake queueing and raw HTML snapshot persistence

## Quick Start

1. Copy env defaults:

```bash
cp .env.example .env
```

2. Create a local Python environment and install backend tooling:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

3. Install frontend dependencies:

```bash
cd services/web
npm install
cd ../..
```

4. Run migrations against whichever Postgres instance `DATABASE_URL` points at:

```bash
source .venv/bin/activate
alembic upgrade head
```

5. Run the services locally in separate terminals:

```bash
source .venv/bin/activate
uvicorn services.api.app.main:create_app --factory --host 0.0.0.0 --port 8000
```

```bash
source .venv/bin/activate
python -m services.worker.app.main
```

```bash
source .venv/bin/activate
python -m services.scheduler.app.main
```

```bash
cd services/web
npm run dev
```

6. Or boot the full local stack with Docker:

```bash
docker compose up --build
```

## Manual URL Intake

Queue a manual HTML snapshot job:

```bash
curl -X POST http://localhost:8000/api/listings/intake/url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com"}'
```

Inspect source snapshots:

```bash
curl http://localhost:8000/api/admin/source-snapshots
```

Inspect queued jobs:

```bash
curl http://localhost:8000/api/admin/jobs
```

## Checks

Backend:

```bash
source .venv/bin/activate
ruff check .
pytest
```

Frontend:

```bash
cd services/web
npm run lint
npm run build
```

## Deployment Notes

- Local/dev uses the `postgres` service from `docker-compose.yml` and the `local` storage backend.
- Production on a VPS should run `api`, `worker`, and `scheduler` only, with `DATABASE_URL` pointed at Supabase Postgres/PostGIS and `STORAGE_BACKEND=supabase`.
- The web app is structured for Netlify deployment with `NEXT_PUBLIC_*` env vars only.
- Supabase Auth is represented through app-level user and role tables keyed by external auth IDs; the API remains the authorization source of truth.

## Deferred To Phase 1+

- compliant listing connectors beyond manual URL intake
- listing parsing, dedupe, and clustering
- site creation and geometry workflows
- planning intelligence, scoring, valuation, and model training

