# land-intel-core

London-first land intelligence monorepo. The controlling spec for this repo is [docs/london_land_intelligence_implementation_spec_v1 (2).md](/Users/atta/land-intel-core/docs/london_land_intelligence_implementation_spec_v1%20(2).md).

Phase 1A is implemented here. That means the repo now covers listing ingestion and clustering only:
- compliant connector framework
- immutable HTML/PDF/CSV snapshots
- listing parsing and normalization
- deterministic dedupe and clustering
- listing list/detail and cluster list/detail APIs
- internal listing and connector UI

Site geometry, title linkage, planning enrichment, scenarios, assessments, scoring, valuation, and model work remain deferred.

## Repo Layout

- `services/api`: FastAPI API
- `services/worker`: Postgres-backed worker loop
- `services/scheduler`: recurring queue writer for approved automated sources with explicit intervals
- `services/web`: Next.js internal analyst UI
- `python/landintel`: shared config, models, connectors, listing pipeline, storage, and readback
- `db/migrations`: Alembic revisions
- `infra/compose`: compose overlays and deployment notes
- `docs`: spec and implementation notes

## Quick Start

1. Copy env defaults:

```bash
cp .env.example .env
```

2. Install backend dependencies:

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

4. Run migrations against your Postgres target:

```bash
source .venv/bin/activate
alembic upgrade head
```

5. Run services locally in separate terminals:

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

6. Or boot the full stack with Docker:

```bash
docker compose up --build
```

## Local Smoke Commands

Queue a manual URL:

```bash
curl -X POST http://localhost:8000/api/listings/intake/url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","source_name":"manual_url"}'
```

Upload a CSV:

```bash
curl -X POST http://localhost:8000/api/listings/import/csv \
  -F source_name=csv_import \
  -F file=@/absolute/path/to/listings.csv
```

Run an approved automated source:

```bash
curl -X POST http://localhost:8000/api/listings/connectors/example_public_page/run \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'
```

Inspect outputs:

```bash
curl http://localhost:8000/api/listings
curl http://localhost:8000/api/listing-clusters
curl http://localhost:8000/api/admin/source-snapshots
curl http://localhost:8000/api/admin/jobs
```

## Source Approval Rules

- `manual_url` uses connector type `MANUAL_URL` and is allowed for manual analyst-triggered intake.
- `csv_import` uses connector type `CSV_IMPORT` and is allowed for analyst-uploaded broker drops.
- automated public-page runs are blocked unless the `listing_source` row exists, is `active = true`, and has `compliance_mode = COMPLIANT_AUTOMATED`
- no domain-specific portal scraper is shipped here; the public-page connector is generic and config-driven from `listing_source.refresh_policy_json`
- scheduler-driven refresh only happens when an approved automated source also has `refresh_policy_json.interval_hours`

Minimal `refresh_policy_json` for an automated source:

```json
{
  "seed_urls": ["https://example.com/land"],
  "listing_link_selector": "a.listing-link",
  "listing_url_patterns": ["/listings/"],
  "max_listings": 10,
  "interval_hours": 6
}
```

## Storage and Immutability

- every connector run creates one `source_snapshot`
- every run stores one or more immutable `raw_asset` rows
- PDFs are stored as raw assets and extracted with PyMuPDF when possible
- raw assets are never overwritten in place; the local storage adapter raises if content changes for an existing path
- existing Phase 0 snapshots remain in place; new Phase 1A snapshots record `parse_status`

## API Surface

- `POST /api/listings/intake/url`
- `POST /api/listings/import/csv`
- `POST /api/listings/connectors/{source_key}/run`
- `GET /api/listings`
- `GET /api/listings/{listing_id}`
- `GET /api/listing-clusters`
- `GET /api/listing-clusters/{cluster_id}`
- `GET /api/admin/listing-sources`
- `GET /api/admin/source-snapshots`
- `GET /api/admin/jobs`

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
npm run typecheck
npm run build
```

Docker + migrations:

```bash
source .venv/bin/activate
DATABASE_URL=postgresql+psycopg://landintel:landintel@localhost:5432/landintel alembic upgrade head
docker compose up --build -d
docker compose ps
```

## Assumptions In This Phase

- listing clustering is intentionally boring and reversible: canonical URL, normalized address, brochure hash, headline similarity, and lat/lon proximity only
- cluster rebuild is a full recompute job; there is no irreversible merge state
- London-first scope is enforced by source selection and analyst workflow, not by a borough geometry filter yet
- missing fields stay null; the parser does not invent planning claims or geometry

## Deferred To Phase 2+

- site creation from clusters
- geometry editing and EPSG:27700 business logic
- HMLR title linkage and LPA linkage
- planning enrichment and extant-permission logic
- scenarios, assessments, scoring, valuation, and training
