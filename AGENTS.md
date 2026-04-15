# AGENTS

## Repo Layout

- `services/api`: FastAPI routes for listings, clusters, sites, scenarios, assessments, admin, and later-phase stubs
- `services/worker`: Postgres-backed worker loop with connector, cluster rebuild, site refresh/linkage, planning enrichment, scenario refresh, historical-label, comparable, replay, and gold-set jobs
- `services/scheduler`: recurring enqueue loop for approved automated listing sources with explicit intervals
- `services/web`: Next.js analyst UI focused on listings, clusters, sites, planning context, scenario editing, hidden-mode assessments, gold-set review, and admin release inspection
- `python/landintel`: shared config, ORM models, connector framework, listing parsing/clustering, geospatial/site services, planning enrichment, evidence assembly, scenarios, assessments, historical labels, storage, and readback
- `db/migrations`: Alembic revisions
- `infra/compose`: local/VPS compose assets
- `docs`: controlling spec and implementation notes

## Run / Build / Test

- Python setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- Backend migrations: `alembic upgrade head`
- Reference bootstrap: `python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev`
- Planning bootstrap: `python -m landintel.planning.bootstrap --dataset all --requested-by local-dev`
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

- Stop at Phase 6A. Do not start Phase 7 valuation / uplift / ranking or Phase 8 overrides / kill switches / visible release controls / broader dashboards.
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
- PLD is supplemental only; borough planning-register data is the authority of record where available.
- Brownfield Part 1 is not PiP. Brownfield Part 2 must stay distinct and can be materially exclusionary.
- Missing source coverage never proves a clean permission, policy, or constraint state.
- If a mandatory source family is missing for a critical permission conclusion, return manual review or abstain.
- LLMs may help summarize evidence, but they must not create authoritative planning facts.
- Scenarios are hypotheses, not facts.
- No standard-analyst visible probability output exists in this phase.
- Hidden scoring is internal-only and must resolve only through `model_release` / `active_release_scope`.
- No valuation or ranking logic belongs in this phase.
- No future leakage in historical labels or point-in-time features.
- Assessment runs require a confirmed scenario and always freeze PIT artifacts before any hidden scoring.
- Preserve provenance for every frozen feature and replay-safe assessment artifact.
- Every operational borough rulepack rule must cite source provenance.
- Confirmed scenarios must freeze the current geometry hash and become stale/review-required after later geometry changes.
- Do not downgrade an abstain/manual-review condition just because a scenario exists.
- If strong nearest historical support cannot be shown honestly, default to `ANALYST_REQUIRED`.

## Phase 6A Done Means

- `docker compose up --build` boots `api`, `worker`, `scheduler`, `web`, and local PostGIS
- `alembic upgrade head` succeeds
- Phase 1A listing ingestion and clustering still pass locally
- local/dev borough and title fixtures can be imported through the reference bootstrap path
- a listing cluster can be converted into a `site_candidate` with an auditable geometry revision
- analysts can save new geometry revisions without overwriting prior evidence
- borough assignment and title linkage are visible in API and UI
- fixture-scale planning, policy, brownfield, flood, heritage, and Article 4 imports run locally
- site detail shows permission state, evidence `FOR` / `AGAINST` / `UNKNOWN`, source coverage warnings, and raw-source links
- extant-permission re-screening works through the API
- the three v1 scenario templates are seeded and supported pilot boroughs expose cited rulepacks
- analysts can suggest, edit, confirm, reject, and inspect scenarios end to end
- scenario-conditioned evidence is visible in the API and web UI
- confirmed scenarios freeze the current geometry hash and become stale when geometry later changes
- historical labels rebuild deterministically on fixture-scale data with explicit exclusion/censoring reasons
- `POST /api/assessments` creates a frozen assessment artifact from a confirmed scenario
- supported templates produce hidden-only scored assessments through an active release scope; unsupported templates remain honest `NOT_READY` releases
- `GET /api/assessments/{id}` returns stable features, evidence, comparables, provenance, replay metadata, and redacted standard reads by default
- hidden mode can surface rounded hidden probability, estimate quality, OOD state, drivers, and release metadata without turning the standard UI into a visible-probability surface
- comparable fallback path is visible and replay verification stays stable for the same frozen inputs
- replay of the same scored assessment reproduces the same feature hash and result payload hash
- the web app renders the site list/detail, MapLibre geometry editor, planning-context panels, scenario editor, assessment view, and gold-set review surface locally
- the web app also exposes hidden assessment mode and the admin model-release registry locally
- tests and lint/build checks pass

## Source Approval Notes

- `manual_url` and `csv_import` are seeded safe sources for analyst-triggered intake only.
- automated sources must exist in `listing_source`, be active, and declare `COMPLIANT_AUTOMATED`.
- scheduler refresh only triggers when an approved automated source also sets `refresh_policy_json.interval_hours`.
