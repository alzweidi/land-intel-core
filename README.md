# land-intel-core

London-first land intelligence monorepo. The controlling spec for this repo is [docs/london_land_intelligence_implementation_spec_v1 (2).md](/Users/atta/land-intel-core/docs/london_land_intelligence_implementation_spec_v1%20(2).md).

Phase 2 is implemented here. The repo now covers the Phase 1A listing pipeline plus auditable site creation and draft geometry:
- compliant connector framework and immutable listing snapshots
- listing parsing, normalization, and deterministic clustering
- site creation from listing clusters
- draft geometry creation and analyst-editable geometry revisions
- London borough / LPA linkage with trivial-vs-material cross-LPA handling
- HMLR INSPIRE title linkage as indicative evidence only
- site list/detail API and internal map/detail UI

Phase 3+ planning evidence, extant-permission logic, policy ingestion, scenarios, assessments, scoring, valuation, and model work remain deferred.

## Repo Layout

- `services/api`: FastAPI API
- `services/worker`: Postgres-backed worker loop
- `services/scheduler`: recurring queue writer for approved automated sources with explicit intervals
- `services/web`: Next.js internal analyst UI
- `python/landintel`: shared config, ORM models, connector framework, listing pipeline, geospatial/site services, storage, and readback
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

5. Bootstrap the local Phase 2 reference fixtures for borough boundaries and title polygons:

```bash
source .venv/bin/activate
python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev
```

6. Run services locally in separate terminals:

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

7. Or boot the full stack with Docker:

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

Inspect listing outputs:

```bash
curl http://localhost:8000/api/listings
curl http://localhost:8000/api/listing-clusters
curl http://localhost:8000/api/admin/source-snapshots
curl http://localhost:8000/api/admin/jobs
```

Create a site candidate from a cluster and inspect it:

```bash
curl -X POST http://localhost:8000/api/sites/from-cluster/<cluster_uuid> \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'

curl http://localhost:8000/api/sites
curl http://localhost:8000/api/sites/<site_uuid>
```

Save a geometry revision:

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/geometry \
  -H 'Content-Type: application/json' \
  -d '{"geom_4326":{"type":"Polygon","coordinates":[[[-0.12,51.52],[-0.119,51.52],[-0.119,51.521],[-0.12,51.521],[-0.12,51.52]]]},"source_type":"ANALYST_DRAWN","confidence":"HIGH","reason":"Analyst correction","created_by":"local-smoke"}'
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
- every reference-data bootstrap run also creates immutable `source_snapshot` and `raw_asset` rows before updating local support tables

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
- `POST /api/sites/from-cluster/{cluster_id}`
- `GET /api/sites`
- `GET /api/sites/{site_id}`
- `POST /api/sites/{site_id}/geometry`

## Reference Data Bootstrap

- `python -m landintel.geospatial.bootstrap --dataset lpa --requested-by local-dev` imports the London borough/LPA fixture set.
- `python -m landintel.geospatial.bootstrap --dataset titles --requested-by local-dev` imports the sample HMLR INSPIRE title polygons.
- `python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev` runs both imports.
- local/dev uses fixture-scale coverage only; this phase does not attempt national bulk ingestion.

## Geometry Confidence Meanings

- `HIGH`: explicit source polygon or carefully analyst-drawn replacement backed by evidence.
- `MEDIUM`: deterministic title-union or other defensible area evidence, but still not legal parcel truth.
- `LOW`: approximate bbox or other coarse geometry that still bounds a candidate.
- `INSUFFICIENT`: point-only or otherwise unusable geometry that needs analyst work before downstream use.

All canonical calculations run in EPSG:27700. EPSG:4326 is stored only for display and export surfaces.

## Phase 2 Rules

- the assessed object is the site geometry, not an individual title polygon
- title polygons are indicative evidence only and can support multi-title linkage
- material cross-LPA overlap requires manual clipping or analyst confirmation
- geometry revisions are append-only and audited; raw assets and source snapshots remain immutable
- do not infer planning truth, policy truth, or parcel-only scoring signals from listing text
- do not use brochure OCR/CV or speculative polygon inference in this phase

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
python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev
docker compose up --build -d
docker compose ps
```

## Assumptions In This Phase

- listing clustering stays intentionally boring and reversible: canonical URL, normalized address, brochure hash, headline similarity, and lat/lon proximity only
- local/dev reference data uses small London fixture files rather than a national bulk import
- when only point evidence exists, the site can be created as `POINT_ONLY` / `INSUFFICIENT`, but it stays clearly flagged for manual work
- missing fields stay null; the parser does not invent planning claims or geometry

## Deferred To Phase 3+

- planning context and evidence pack generation
- extant-permission engine
- PLD / borough planning-register ingestion
- Planning Data constraint and policy-layer ingestion
- scenario suggestion or confirmation
- assessments, scoring, valuation, ranking, and model training
