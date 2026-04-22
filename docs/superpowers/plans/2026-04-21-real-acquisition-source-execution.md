# Phase 8A Real Acquisition Source Execution Plan

**Goal:** Make the Phase 8A stack truthfully surface real London land-for-sale candidates for the acquisition brief by onboarding at least one compliant automated source that actually yields parcel-grade opportunities, preserving strict source-fit controls, and proving the live end-to-end flow in API and web surfaces.

**Scope guard:** Stay inside Phase 8A. No portal-specific scrapers without explicit compliance approval. No weakening of abstain/manual-review, hidden-probability, immutable snapshot, or scheduler-compliance guardrails.

## Assumptions

- The current Cabinet Office source remains compliant but is insufficient for the acquisition brief unless upstream inventory has materially changed.
- Full success requires a source whose automated terms and real live inventory both fit the brief.
- If no compliant automated source with qualifying live London parcel inventory exists, the correct outcome is to preserve truthful zero/hold states and report the exact blocker with evidence rather than degrade controls.

## Execution Slices

1. Source proof
   - Re-check current approved automated feeds and research additional compliant automated candidate feeds.
   - Verify compliance posture, automation feasibility, live access pattern, London coverage, parcel-grade fit, and live source-page linkability.
   - Select exactly one source only if it honestly satisfies the acquisition brief.

2. Backend intake and filtering
   - Extend or add connector support only for the selected compliant automated source.
   - Preserve immutable `source_snapshot` / `raw_asset` / `listing_snapshot` behavior.
   - Add source-specific parcel-grade filters to block buildings, sold stock, estate-wide zones, operational sites, and stale inventory.
   - Ensure listing `canonical_url` remains the live source URL through readback.

3. Site promotion and pipeline truthfulness
   - Tighten auto-promotion so only bounded land opportunities progress into `site_candidate`.
   - Keep geometry requirements strict and avoid title-union inflation.
   - Run existing planning/scenario/assessment flows without fabricating permission certainty where coverage is incomplete.

4. API and web surfacing
   - Show real live-source rows in listings, site, and opportunity surfaces.
   - Expose direct click-through source links.
   - Preserve honest empty/hold/manual-review states where the pipeline lacks qualifying evidence.

5. Verification and readiness
   - Run backend and web verification suites.
   - Bring up the docker stack, migrate, trigger live source refresh, and smoke-test API/UI behavior.
   - Conclude with a readiness decision tied to live evidence, not intent.

## Outcome

- Implemented `ideal_land_current_sites` as a compliant automated public-page source with source-specific extraction and parcel-grade source-fit rules, then extended the generic connector to discover listing links from first-party sitemaps so it can exhaust truthful live inventory instead of only the seed page.
- Implemented `bidwells_land_development` as a second compliant automated public-page source with strict source-fit controls: first-party sitemap only, London bbox requirement, brochure requirement, point-coordinate requirement, and exclusions for sold / under-offer / consented / broad non-target stock.
- Hardened the generic public-page connector so stale or dead listing URLs discovered from a compliant sitemap are recorded and skipped instead of aborting the entire automated source run. This was required because Ideal Land currently publishes multiple dead listing URLs in its sitemap.
- Hardened document parsing and page capture to retain live brochure URLs and tolerate broken optional brochure links without failing the source job.
- Verified the live automated runs now create truthful immutable `source_snapshot`, `raw_asset`, listing, cluster, and site records and preserve the live listing `canonical_url` through API and web readback.
- Verified the live stack now surfaces:
  - one real Ideal Land listing and cluster:
    - `Fishponds Road, Tooting, SW17`
    - source URL `https://idealland.co.uk/properties/fishponds-road-tooting-sw17`
  - one real Bidwells listing, cluster, and auto-promoted site candidate:
    - `Land South Of Thames Road, Crayford, Dartford, DA1 5FH`
    - source URL `https://www.bidwells.co.uk/properties/land-south-of-thames-road-crayford/rps_bid-RUR250274`
- Verified the Bidwells site candidate is created truthfully but only as:
  - `geom_source_type = POINT_ONLY`
  - `geom_confidence = INSUFFICIENT`
  - `site_status = INSUFFICIENT_GEOMETRY`
  - manual review required
- Verified the live scenario pipeline stops honestly on the real Bidwells site:
  - `POST /api/sites/{site_id}/scenarios/suggest` returns no scenario items and excludes all templates with `RULEPACK_MISSING`.
- Verified the local Phase 8A bootstraps are genuinely pilot-scale:
  - LPA boundary fixture imports only `camden`, `islington`, and `southwark`
  - HMLR title fixture imports only three title polygons
  - baseline packs exist only for `camden` and `southwark`
- Verified the current live Bidwells site sits in Bexley, outside the local pilot planning footprint, so the planning path abstains honestly with unresolved borough / mandatory-source coverage warnings.
- Re-checked additional first-party compliant public inventory for Camden / Islington / Southwark. As of `2026-04-21`, no checked live source produced a parcel-grade, currently available, unconsented, Phase-8A-usable candidate in those boroughs:
  - Strettons had live target-borough pages, but they were investment stock, under-offer stock, or non-target assets rather than honest parcel-grade development opportunities.
  - Gilmartin Ley, Linays, Bidwells, Knight Frank, and Savills did not produce a verified current target-borough candidate that cleared both compliance and acquisition-fit checks.

## Readiness Implication

- This slice improves the system materially and truthfully, but it does **not** fully satisfy the acquisition brief yet.
- The remaining blocker is now precise and evidenced:
  - the repo’s Phase 8A local planning fixtures only support a pilot borough footprint (`camden`, `islington`, `southwark`)
  - the currently verified compliant live parcel-grade candidates fall outside that footprint or lack enough geometry evidence to progress beyond honest manual-review states
  - no checked first-party compliant source currently exposes a Camden / Islington / Southwark parcel-grade listing that is both live and usable under the repo rules
- Under the spec, the correct behavior is therefore to preserve truthful listing / cluster / site surfaces and abstain from scenario / assessment / visible-probability rollout rather than fabricate planning certainty.

## Continuation Slice

- Re-check current-date first-party source inventory for additional compliant London parcel listings, with emphasis on sources that expose coordinates, brochures, title clues, or site plans.
- Re-evaluate whether the current Bexley Bidwells site can progress honestly through the existing geometry and planning gates using already-supported official evidence paths.
- Inspect the repo’s planning bootstrap and borough/rulepack footprint to determine whether adding truthful local-dev coverage for one more borough is an in-scope Phase 8A implementation step or still blocked by missing authoritative packs.
- Only ship further code if it closes one of those gaps without weakening the Phase 8A guardrails. Otherwise, keep the current implementation and report the exact blocker with fresh evidence.

## 2026-04-22 Continuation

- Confirmed the existing generic public-page connector can fetch and parse live Savills development-land pages from the runtime without a new portal scraper.
- Added `savills_development_land` as a compliant automated first-party source, limited to the Camden / Islington / Southwark Savills borough development-land index pages and linked detail pages.
- Proved a first live Savills run was too broad: the borough seed pages surfaced additional London redevelopment stock outside the intended target slice, and the original source-fit policy did not block rows whose normalized `listing.status` was `UNDER_OFFER`.
- Hardened the Savills source-fit path by adding connector-level support for:
  - `required_listing_statuses`
  - `require_map_asset`
- Tightened Savills policy to require:
  - `listing.status` in `LIVE` or `AUCTION`
  - point coordinates
  - address text
- This first Savills tightening proved too strict on live data:
  - `Camden Park House, 57-59 Camden Park Road, London` is a live in-scope first-party land listing with coordinates and parcel-grade fit, but Savills does not expose a separate map / plan PDF for that page.
  - the `require_map_asset` gate therefore hid a truthful Camden candidate rather than blocking a false positive.
- Added a backfill migration so existing databases update the Savills source policy in place instead of retaining the earlier looser fit.
- Reset the local docker Postgres / raw-storage volumes after the first loose Savills run so the next live verification runs against a clean database rather than stale over-broad Savills rows.
- Current continuation boundary:
  - code changes are in place for Savills onboarding and fit hardening
  - focused tests for the new Savills migrations and connector-fit branches pass
  - the full `pytest` rerun from the latest code still needs the final coverage closures for `public_page.py`, `parsing.py`, and the existing uncovered `sites/service.py` branches
  - the clean-state live bootstrap and source-refresh verification still need to be completed and recorded from the rebuilt stack

## 2026-04-22 Final Continuation

- Closed the remaining Savills/runtime-filter correctness gaps:
  - `max_listings` now applies after source-fit acceptance instead of truncating candidate URLs before fit evaluation.
  - duplicate PDF links now preserve `MAP` classification when the same asset appears under both brochure and plan labels.
  - runtime LPA filtering now fails closed if any configured borough boundary is missing instead of silently narrowing scope.
  - Savills fit-backfill downgrade behavior now restores the revision-17 policy instead of loosening it.
- Added `20260422_000019_phase8a_savills_scope_repair` to repair existing databases that had already reached head before `required_lpa_ids` was present in the Savills source policy.
- Fixed a date-sensitive valuation-opportunity test by freezing the test clock instead of depending on `date.today()`.
- Rebuilt the Docker stack from scratch on a wiped Postgres / raw-storage volume and re-ran the local bootstrap against the corrected migrations.
- Verified the durable Savills policy now keeps strict status / borough / coordinate / address filtering but no longer requires a separate map asset, which allows the truthful Camden listing through while still rejecting the Lambeth false positive at runtime.
- Added a dedicated Phase 8A live-planning bootstrap bundle for the local runtime:
  - `tests/fixtures/planning/borough_register_phase8a_live.json`
  - `tests/fixtures/planning/brownfield_sites_phase8a_live.geojson`
  - `tests/fixtures/planning/baseline_packs_phase8a_live.json`
- Updated `scripts/setup_local.sh` to use that live-planning fixture bundle by default and to refresh the approved automated sources (`savills_development_land`, `bidwells_land_development`, `ideal_land_current_sites`) in one truthful bootstrap flow.
- Verified the live stack now surfaces four real listings:
  - `Camden Park House, 57-59 Camden Park Road, London` from Savills
  - `2 Hamilton Lane, Highbury, N5 1SH` from Savills
  - `Fishponds Road, Tooting, SW17` from Ideal Land
  - `Land South Of Thames Road, Crayford, Dartford, DA1 5FH` from Bidwells
- Verified the live stack now serves:
  - `3` listing clusters
  - `3` site candidates
  - `3` opportunities
- Verified the live site paths now split into two honest states:
  - `Camden Park House` reaches truthful site creation but remains `Hold` because analyst confirmation is still required before assessment (`NEAREST_HISTORICAL_SUPPORT_NOT_STRONG`).
  - `2 Hamilton Lane, Highbury, N5 1SH` now has truthful title-union geometry at `1078.3 sqm`, fits the `resi_5_9_full` area band, reaches scenario suggestion, analyst confirmation, and assessment creation, and surfaces in opportunities as `Band B`.
- Verified the latest Savills runtime manifest still blocks the off-scope Lambeth false positive through `required_lpa_ids = ['camden', 'islington', 'southwark']`.
- Verified the end-to-end live planning path now works for the real Hamilton Savills site:
  - scenario suggestion returned `resi_5_9_full`
  - analyst confirmation succeeded
  - `POST /api/assessments` created assessment `65ebccf6-7f71-59fc-8e37-2e145030c435`
  - the assessment is `READY` with `score_execution_status = HIDDEN_ESTIMATE_AVAILABLE`
  - the opportunity surface now shows `Band B` for Hamilton while remaining `hidden_mode_only = true`
- Verified the remaining live holds stay truthful:
  - `Camden Park House` still requires analyst confirmation before any assessment
  - `Land South Of Thames Road, Crayford, Dartford, DA1 5FH` remains blocked by missing mandatory `BOROUGH_REGISTER` coverage for the controlling borough
- Final verification on the completed stack:
  - `ruff check .`
  - `pytest` (`420 passed in 453.78s`, `100.00%` coverage)
  - `cd services/web && npm run lint`
  - `cd services/web && npm run typecheck`
  - `cd services/web && npm run test:coverage`
  - `cd services/web && npm run build`
  - `docker compose up --build -d`
  - `DATABASE_URL='postgresql+psycopg://landintel:landintel@localhost:5432/landintel' alembic upgrade head`
  - `BACKEND_BASIC_AUTH_USER=local BACKEND_BASIC_AUTH_PASSWORD=local bash scripts/smoke_prod.sh http://localhost:3000 http://localhost:8000`
- End state for this slice:
  - the local stack is now up with `api`, `web`, `worker`, `scheduler`, and PostGIS running
  - at least one real compliant automated source now yields a real pilot-borough candidate that reaches assessment and opportunity ranking truthfully
  - visible probability remains blocked per Phase 8A scope rules, while the live opportunity surface exposes only the allowed hidden-mode banding behavior
