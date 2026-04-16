# land-intel-core

London-first land intelligence monorepo. The controlling spec for this repo is [docs/london_land_intelligence_implementation_spec_v1 (2).md](/Users/atta/land-intel-core/docs/london_land_intelligence_implementation_spec_v1%20(2).md).

Phase 8A is implemented here. The repo now covers the Phase 1A listing pipeline, Phase 2 site geometry, Phase 3A planning context, Phase 4A scenario foundations, Phase 5A assessment foundations, Phase 6A hidden-only scoring, the Phase 7A valuation/ranking layer, and the Phase 8A safety/control plane:
- compliant connector framework and immutable listing snapshots
- listing parsing, normalization, and deterministic clustering
- site creation from listing clusters
- draft geometry creation and analyst-editable geometry revisions
- London borough / LPA linkage with trivial-vs-material cross-LPA handling
- HMLR INSPIRE title linkage as indicative evidence only
- fixture-scale planning, policy, brownfield, flood, heritage, and Article 4 imports
- deterministic site planning enrichment and source-coverage tracking
- auditable extant-permission screening with `FOR` / `AGAINST` / `UNKNOWN` evidence assembly
- seeded v1 scenario templates, cited pilot-borough rulepacks, and deterministic scenario suggestions
- analyst scenario edit / confirm / reject workflow with frozen geometry hash and stale-state handling
- scenario-conditioned evidence in API and internal UI
- site list/detail API and internal map/detail UI with planning and scenario panels
- historical label construction with explicit positive / negative / excluded mappings
- point-in-time feature snapshots with provenance, missingness flags, and stable feature hashing
- frozen assessment runs with deterministic comparable retrieval and replay-safe prediction-ledger rows
- minimal gold-set review APIs and internal review surface
- hidden-only logistic-regression releases with calibration artifacts, OOD logic, estimate quality, explanation payloads, and replay-safe release resolution
- versioned valuation assumption sets with fixture-scale HMLR Price Paid, UKHPI rebasing, and supplementary land comp evidence
- immutable valuation runs/results with residual land value, uplift, sense-check divergence handling, and valuation-quality logic
- planning-first opportunity ranking with honest HOLD states when no active hidden release or sufficient valuation basis exists
- append-only assessment overrides that preserve original frozen results side-by-side with effective override readback
- scope visibility gating, incident controls, audit-export manifests, and local admin health/model/economic readbacks
- hidden-vs-visible redaction logic with reviewer-only visible mode blocked by default on current fixture-scale local/dev data

Broader operational signoff and real visible-pilot readiness remain deferred even though the Phase 8A code paths now exist.

Production deployment hardening assets now live in [DEPLOY.md](/Users/atta/land-intel-core/DEPLOY.md:1) and [OPERATIONS.md](/Users/atta/land-intel-core/OPERATIONS.md:1).

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

6. Bootstrap the local Phase 3A through Phase 8A planning fixtures:

```bash
source .venv/bin/activate
python -m landintel.planning.bootstrap --dataset all --requested-by local-dev
```

7. Rebuild hidden model releases for the current fixture corpus:

```bash
curl -X POST http://localhost:8000/api/admin/model-releases/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-dev","auto_activate_hidden":true}'
```

8. Bootstrap fixture-scale valuation data and seeded assumption sets:

```bash
source .venv/bin/activate
python -m landintel.valuation.bootstrap --dataset all --requested-by local-dev
```

9. Run services locally in separate terminals:

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

10. Or boot the full stack with Docker:

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

Run an extant-permission recheck and inspect planning data health:

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/extant-permission-check \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'

curl http://localhost:8000/api/health/data
```

Save a geometry revision:

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/geometry \
  -H 'Content-Type: application/json' \
  -d '{"geom_4326":{"type":"Polygon","coordinates":[[[-0.12,51.52],[-0.119,51.52],[-0.119,51.521],[-0.12,51.521],[-0.12,51.52]]]},"source_type":"ANALYST_DRAWN","confidence":"HIGH","reason":"Analyst correction","created_by":"local-smoke"}'
```

Suggest, inspect, and confirm scenarios:

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/scenarios/suggest \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'

curl http://localhost:8000/api/sites/<site_uuid>/scenarios
curl http://localhost:8000/api/scenarios/<scenario_uuid>

curl -X POST http://localhost:8000/api/scenarios/<scenario_uuid>/confirm \
  -H 'Content-Type: application/json' \
  -d '{"action":"confirm","reviewed_by":"local-smoke","review_notes":"Analyst confirmed after reviewing rulepack fit."}'
```

Create and inspect a frozen assessment, then open hidden mode explicitly:

```bash
curl -X POST http://localhost:8000/api/assessments \
  -H 'Content-Type: application/json' \
  -d '{"site_id":"<site_uuid>","scenario_id":"<confirmed_scenario_uuid>","as_of_date":"2026-04-15","requested_by":"local-smoke"}'

curl http://localhost:8000/api/assessments
curl http://localhost:8000/api/assessments/<assessment_uuid>
curl 'http://localhost:8000/api/assessments/<assessment_uuid>?hidden_mode=true'
curl http://localhost:8000/api/admin/model-releases
```

Inspect planning-first opportunity ranking:

```bash
curl http://localhost:8000/api/opportunities
curl http://localhost:8000/api/opportunities/<site_uuid>
```

Inspect and review gold-set cases:

```bash
curl http://localhost:8000/api/admin/gold-set/cases
curl http://localhost:8000/api/admin/gold-set/cases/<case_uuid>

curl -X POST http://localhost:8000/api/admin/gold-set/cases/<case_uuid>/review \
  -H 'Content-Type: application/json' \
  -d '{"review_status":"CONFIRMED","review_notes":"Fixture review","reviewed_by":"local-smoke"}'
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
- `POST /api/sites/{site_id}/extant-permission-check`
- `POST /api/sites/{site_id}/scenarios/suggest`
- `GET /api/sites/{site_id}/scenarios`
- `GET /api/scenarios/{scenario_id}`
- `POST /api/scenarios/{scenario_id}/confirm`
- `POST /api/assessments`
- `GET /api/assessments`
- `GET /api/assessments/{assessment_id}`
- `GET /api/admin/gold-set/cases`
- `GET /api/admin/gold-set/cases/{case_id}`
- `POST /api/admin/gold-set/cases/{case_id}/review`
- `GET /api/admin/model-releases`
- `GET /api/admin/model-releases/{release_id}`
- `POST /api/admin/model-releases/rebuild`
- `POST /api/admin/model-releases/{release_id}/activate`
- `POST /api/admin/model-releases/{release_id}/retire`
- `GET /api/health/model`
- `GET /api/health/data`
- `GET /api/admin/review-queue`
- `POST /api/assessments/<assessment_uuid>/override`
- `GET /api/assessments/<assessment_uuid>/audit-export`

## Reference Data Bootstrap

- `python -m landintel.geospatial.bootstrap --dataset lpa --requested-by local-dev` imports the London borough/LPA fixture set.
- `python -m landintel.geospatial.bootstrap --dataset titles --requested-by local-dev` imports the sample HMLR INSPIRE title polygons.
- `python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev` runs both imports.
- `python -m landintel.planning.bootstrap --dataset pld --requested-by local-dev` imports fixture-scale London Datahub records.
- `python -m landintel.planning.bootstrap --dataset borough-register --requested-by local-dev` imports the pilot borough register fixture set.
- `python -m landintel.planning.bootstrap --dataset brownfield --requested-by local-dev` imports brownfield state fixtures with Part 1 and Part 2 separated.
- `python -m landintel.planning.bootstrap --dataset policy --requested-by local-dev` imports London DataMap / borough policy area fixtures.
- `python -m landintel.planning.bootstrap --dataset constraints --requested-by local-dev` imports Planning Data, flood, heritage, and Article 4 fixtures.
- `python -m landintel.planning.bootstrap --dataset baseline --requested-by local-dev` imports cited pilot-borough baseline packs and machine-readable rulepacks.
- `python -m landintel.planning.bootstrap --dataset all --requested-by local-dev` runs the full Phase 3A through Phase 8A planning fixture bootstrap.
- `python -m landintel.valuation.bootstrap --dataset hmlr-price-paid --requested-by local-dev` imports fixture-scale HMLR Price Paid evidence with provenance.
- `python -m landintel.valuation.bootstrap --dataset ukhpi --requested-by local-dev` imports fixture-scale UKHPI rebasing series.
- `python -m landintel.valuation.bootstrap --dataset land-comps --requested-by local-dev` imports supplementary permissioned land/auction/benchmark fixture evidence.
- `python -m landintel.valuation.bootstrap --dataset assumptions --requested-by local-dev` seeds the default versioned valuation assumption set.
- `python -m landintel.valuation.bootstrap --dataset all --requested-by local-dev` runs the full Phase 7A valuation fixture bootstrap.
- local/dev uses fixture-scale coverage only; this phase does not attempt national bulk ingestion.

## Geometry Confidence Meanings

- `HIGH`: explicit source polygon or carefully analyst-drawn replacement backed by evidence.
- `MEDIUM`: deterministic title-union or other defensible area evidence, but still not legal parcel truth.
- `LOW`: approximate bbox or other coarse geometry that still bounds a candidate.
- `INSUFFICIENT`: point-only or otherwise unusable geometry that needs analyst work before downstream use.

All canonical calculations run in EPSG:27700. EPSG:4326 is stored only for display and export surfaces.

## Scenario Templates And Rulepacks

- Phase 4A seeds the exact v1 templates from the controlling spec:
  - `resi_1_4_full`
  - `resi_5_9_full`
  - `resi_10_49_outline`
- pilot borough rulepacks are stored as machine-readable operational summaries, not law
- every operational rule must carry source provenance in the stored citation payload
- rulepack freshness and status are exposed through site readback and `/api/health/data`

## Scenario Statuses

- `SUGGESTED`: deterministic heuristic output awaiting analyst action
- `AUTO_CONFIRMED`: only allowed when all conservative gates are satisfied; this phase defaults to `ANALYST_REQUIRED` when strong nearest historical support cannot be proven
- `ANALYST_CONFIRMED`: analyst-reviewed scenario, possibly with edits
- `ANALYST_REQUIRED`: viable hypothesis but not safely auto-confirmable
- `REJECTED`: analyst explicitly rejected the scenario
- `OUT_OF_SCOPE`: scenario blocked by extant-permission or other exclusionary context

## Scenario Staleness

- confirmed scenarios freeze the current `red_line_geom_hash`
- if the site geometry changes later, current scenarios are marked stale and review-required rather than silently carried forward
- stale-state is surfaced in the API/UI with warning codes and audit history

## Historical Labels And Assessments

- the historical label target is the first substantive decision within 18 months of validation
- positive labels: approve, conditional approve, and operationally mapped resolve-to-grant / minded-to-grant outcomes
- negative labels: refuse
- excluded or censored: withdrawn, invalid, duplicate/administrative, undetermined beyond the window, appeal-only outcomes, and non-relevant application types
- borough register data remains the authority of record where available; PLD is supplemental only
- point-in-time features use only information available on or before the frozen `as_of_date`
- replay of the same frozen assessment input must reproduce the same feature hash and payload hash
- assessment runs require a confirmed scenario and always freeze the same PIT artifacts for the same inputs
- hidden scoring resolves only through `model_release` and `active_release_scope`
- hidden probability stays redacted on standard reads and is only exposed via explicit hidden mode
- comparable retrieval is deterministic explanation infrastructure only, not a substitute model

## Hidden Release Behavior

- hidden releases are rebuilt from deterministic historical labels and frozen PIT feature snapshots only
- the champion model is a regularized logistic regression over explicit, versioned, interpretable features
- each release stores immutable model, calibration, validation, and model-card artifacts through the storage abstraction
- a release is activatable only when validation completes honestly for that template family; otherwise it remains `NOT_READY` with stored reasons
- replay uses the frozen feature snapshot, resolved release metadata, and ledger payload hash to verify the same assessment can be reproduced exactly

## Phase 8A Rules

- the assessed object is the site geometry, not an individual title polygon
- title polygons are indicative evidence only and can support multi-title linkage
- material cross-LPA overlap requires manual clipping or analyst confirmation
- geometry revisions are append-only and audited; raw assets and source snapshots remain immutable
- PLD is supplemental only; borough planning-register data is the authority of record where available
- Brownfield Part 1 is not PiP; Brownfield Part 2 stays distinct and can be materially exclusionary
- missing source coverage never proves no permission, no policy issue, or no constraint
- missing mandatory source families must return manual review or abstain, not a silent clean state
- do not infer planning truth, policy truth, or parcel-only scoring signals from listing text
- do not use brochure OCR/CV, speculative polygon inference, or LLM-generated planning facts in this phase
- scenarios are hypotheses, not facts
- visible probability stays off by default and may only be exposed through explicit scoped visibility controls
- hidden scoring is allowed only for confirmed scenarios through an active hidden release scope
- valuation runs are immutable and tied to the frozen assessment plus a versioned valuation assumption set
- if acquisition basis is missing, post-permission value may still be produced but uplift stays null and valuation quality is downgraded
- if no active hidden release exists, do not fabricate a planning band or expected uplift; keep the case in `Hold`
- ranking is planning-first: economics never leapfrog a stronger planning band
- overrides are append-only and must never mutate the original model result, valuation run, or ledger payload in place
- visible publication must be blocked if replay fails, artifact hashes mismatch, an incident is open, or scope visibility is disabled
- reviewer-visible mode must stay honest: current fixture-scale local/dev data remains hidden-only unless a qualifying borough/template scope is explicitly signed off
- do not downgrade an `ABSTAIN` / manual-review condition just because a scenario exists
- if strong nearest historical support cannot be shown honestly, default to `ANALYST_REQUIRED`
- if support is insufficient for a template, register an explicit `NOT_READY` release instead of pretending validation passed

## Implemented Source Families

- London Datahub ingest and normalization
- pilot borough planning-register ingest and normalization
- brownfield enrichment
- policy-layer enrichment
- Planning Data constraint enrichment
- flood enrichment
- heritage / Article 4 enrichment
- borough source-coverage capture, freshness state, baseline-pack structure, and cited pilot rulepacks

## Extant Permission Outcomes

- `ACTIVE_EXTANT_PERMISSION_FOUND`: authoritative active material overlap is present.
- `NO_ACTIVE_PERMISSION_FOUND`: no active material overlap was found and mandatory source coverage is complete enough for that conclusion.
- `NON_MATERIAL_OVERLAP_MANUAL_REVIEW`: overlap exists but does not meet the spec materiality threshold.
- `UNRESOLVED_MISSING_MANDATORY_SOURCE`: a mandatory source family is missing or incomplete for a critical conclusion.
- `CONTRADICTORY_SOURCE_MANUAL_REVIEW`: source families disagree in a way that requires analyst review.

The result is always returned with source-coverage context, evidence items, and raw-source links. “Not found” alone is never treated as sufficient evidence.

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
python -m landintel.planning.bootstrap --dataset all --requested-by local-dev
docker compose up --build -d
docker compose ps
```

## Assumptions In This Phase

- listing clustering stays intentionally boring and reversible: canonical URL, normalized address, brochure hash, headline similarity, and lat/lon proximity only
- local/dev reference data uses small London fixture files rather than a national bulk import
- when only point evidence exists, the site can be created as `POINT_ONLY` / `INSUFFICIENT`, but it stays clearly flagged for manual work
- missing fields stay null; the parser does not invent planning claims or geometry
- Phase 3A planning imports stay fixture-scale for local/dev and focus on deterministic site enrichment, not citywide production ingest
- Phase 4A scenario suggestions stay deterministic, testable, and config-driven; they are not predictions
- Phase 6A hidden releases stay honest: supported templates can score in hidden mode, unsupported templates remain `NOT_READY`
- Phase 7A/8A valuation stays honest: missing acquisition basis keeps uplift null, and missing active hidden release keeps opportunities in `Hold`
- hidden-mode scoring is internal only and standard assessment reads stay non-speaking by default
- pilot borough rulepacks are usable operational summaries for fixture boroughs, but they are not a substitute for analyst judgment or legal advice
- fixture-scale valuation evidence uses HMLR Price Paid and UKHPI as mandatory official sources, with land comps as supplementary evidence only
- current fixture-scale local/dev data is still not an honest basis for a broader visible-probability rollout

## Deferred To Operational Signoff / Later Work

- broader gold-set tooling and larger review workflow UX
- richer historical backfill and point-in-time reconstruction coverage
- feature snapshots for model training beyond the frozen Phase 5A artifact path
- standard-analyst visible probability rollout
- broader hidden-mode operations and production release operations
- broader borough/template signoff and real visible-pilot readiness
- comparable-case ranking logic
- broader historical backfill and richer release operations
