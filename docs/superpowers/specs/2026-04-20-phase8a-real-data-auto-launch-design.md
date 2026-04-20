# Phase 8A Real Data Auto-Launch Design

## Goal

Make the current Phase 8A system capable of running a truthful internal launch where:
- real data refresh no longer depends on manual CSV/download workflows for the supported source families
- compliant listed opportunities can flow from intake to site, scenario, assessment, and opportunity surfaces with minimal human intervention
- the web UI can show real internal opportunities and hidden/internal planning probability states without broadening standard analyst-visible probability beyond existing Phase 8A rules

## Scope Boundary

This design stays inside the repo's Phase 8A constraints.

In scope:
- compliant automated listed-source intake
- automated official-data refresh for source families that are already required by Phase 8A and available through licensable/public channels
- automatic queue chaining from listing cluster to site candidate to scenario suggestion to assessment build when the scenario is safe to auto-confirm
- internal opportunity surfacing with honest hold/manual-review states
- admin/runtime controls and documentation needed to operate the above in a local/internal production deployment

Out of scope:
- off-market sourcing
- portal-specific scrapers without explicit compliance approval
- public SaaS rollout
- broad visible-probability rollout for standard analyst users
- later site-assembly or parcel-only expansion work

## Truthful Launch Position

The repo already supports most of the Phase 8A decision stack, but it does not yet contain any real compliant automated listed source beyond the seeded placeholder. That means a fully populated real opportunity queue cannot be achieved honestly by code changes alone unless at least one real compliant listed source is onboarded.

Therefore the launch design has two concurrent data planes:

1. Official-data plane
- bring real planning/reference/valuation inputs onto automated or one-command reproducible refresh paths using official/licensable endpoints where available
- remove manual download/import from the routine operational path for the supported families

2. Listed-opportunity plane
- onboard at least one real source that is both:
  - currently listed land or land-like redevelopment inventory
  - explicitly acceptable for automated use under the repo's compliance model
- only this plane is allowed to create acquisition opportunities in Phase 8A

The first viable source identified for that listed-opportunity plane is the Cabinet Office monthly
`Surplus Property` extract published under the Open Government Licence via
`https://data.insite.cabinetoffice.gov.uk/insite/Register.xlsx`. It is current, public, and
contains London surplus-property rows with sale-status, coordinates, and contact metadata.

If no compliant listed source can be onboarded truthfully, the system can still be made operationally ready, but it cannot honestly present a frontend full of real acquisition opportunities.

## Recommended Source Strategy

### Official sources

Use official/open sources where licensing is clear and the data fits an existing Phase 8A family.

Initial targets:
- HM Land Registry Price Paid Data
- UK House Price Index
- HM Land Registry INSPIRE Index Polygons
- planning.data.gov.uk brownfield and related published datasets where the repo can use them as supplemental/reference evidence
- London/England official boundary and reference layers where they can replace or augment fixture-only local inputs

These sources improve valuation, title linkage, geometry/reference context, and evidence quality, but they do not replace the need for currently listed acquisition channels.

### Listed sources

The first live listed-source rollout must use a generic public-page or feed path only when all are true:
- the source is demonstrably current and relevant to land or land-like redevelopment opportunities
- the source can be automated without violating terms or the repo's compliance rules
- the source is configured through `listing_source` as `COMPLIANT_AUTOMATED`
- the connector remains generic/config-driven, not a bespoke portal scraper

The repo should not self-upgrade random commercial property portals into compliant automated sources without a defensible approval basis.

For this launch slice, the preferred implementation is a generic HTTPS tabular-feed connector
configured against the Cabinet Office `Surplus Property` workbook rather than a bespoke portal
scraper. That keeps the automation path within both the repo's compliance model and the Phase 8A
constraint against portal-specific scrapers without explicit approval.

## End-to-End Automation Design

### Current reality

Today the pipeline already covers:
- source run -> immutable ingestion artifacts
- cluster rebuild
- manual cluster-to-site promotion
- scenario suggestion with `AUTO_CONFIRMED` support
- assessment building from confirmed scenarios
- hidden/internal scoring and opportunity readback

### Required launch chain

Add a deterministic worker-managed automation chain:

1. source refresh job persists listings and raw artifacts
2. cluster rebuild recomputes listing clusters
3. eligible live land-like clusters auto-enqueue `SITE_BUILD_REFRESH`
4. site build refresh creates or refreshes the `site_candidate`
5. site build refresh auto-enqueues scenario suggestion
6. scenario suggestion runs normal Phase 8A rules
7. if a current non-stale scenario is `AUTO_CONFIRMED`, automatically build or refresh the assessment for today's `as_of_date`
8. resulting READY assessments appear in the planning-first opportunity queue
9. scenarios that are not safely auto-confirmable stay in review/manual states rather than being silently published

## Cluster Auto-Promotion Rules

Auto-promotion must be deliberately narrow.

A listing cluster is eligible for automatic site build only when:
- the current listing status is live/auction-like rather than withdrawn or sold-stc
- the listing type is one of:
  - `LAND`
  - `LAND_WITH_BUILDING`
  - `REDEVELOPMENT_SITE`
  - optionally `GARAGE_COURT` if existing Phase 8A scenario templates support it without special-case logic
- the cluster has a current listing and enough geometry/address evidence to derive a site candidate using the existing site build logic

Everything else remains in listings/clusters for analyst review.

## Assessment Auto-Build Rules

Auto-building an assessment is allowed only when the existing rules already permit a speaking-quality scenario state internally.

A site qualifies for automatic assessment build when:
- it has a current, non-stale scenario
- the scenario status is `AUTO_CONFIRMED`
- the scenario geometry hash still matches the site geometry hash
- the build is idempotent for `(site, scenario, as_of_date)`

`ANALYST_REQUIRED` and `ANALYST_CONFIRMED` scenarios remain analyst-driven for assessment creation unless already created manually.

## Probability And Visibility

This launch does not broaden standard visible probability.

Launch behavior:
- hidden/internal probability remains available through the existing release/scope logic
- the standard opportunities queue continues to show planning-first ranking with honest hold/manual-review states
- reviewer/admin hidden mode can inspect internal probability where the current Phase 8A controls already allow it
- nothing in this launch should bypass incidents, replay guards, or scope-visibility rules

## Official Data Refresh Design

The current planning and valuation refresh jobs are mostly fixture-only wrappers. Replace that with a dual-mode design:

- local/dev fixtures remain supported for tests and reproducible local demos
- real refresh mode uses configured remote URLs or manifests for supported official datasets

The remote refresh path should:
- fetch the upstream artifact over HTTP(S)
- persist a `source_snapshot` and immutable `raw_asset`
- normalize/import through the existing source-family import functions where possible
- record coverage/parse/import summary into job payloads

Initial practical objective:
- valuation data refresh becomes real and automatic first
- at least one real reference/geometry family becomes automatic
- planning-source refreshes become remote-configurable where authoritative/public feeds exist, while still preserving abstain/manual-review behavior when authority-grade coverage is missing

## Admin And Web Requirements

The web app should be sufficient for an internal operator to verify that the system is actually live.

Required visible outcomes:
- source-runs/admin pages show live source and job truth, not fixtures
- listings and listing clusters show live imported rows from the compliant source set
- sites page shows auto-created site candidates rather than requiring API-only promotion
- opportunities page shows real internal opportunities or honest empty/hold/manual-review states from live data
- assessment detail remains hidden-safe but available for reviewer/admin workflows
- health/review/admin surfaces expose enough source freshness and job status to operate the system without shell-only inspection

## Testing And Verification

The launch slice must ship with:
- backend tests for cluster auto-promotion, scenario auto-suggest chaining, and auto-assessment creation
- backend tests for official-data remote refresh helpers and fallback-to-fixture behavior
- web tests for live state rendering on listings, sites, opportunities, and admin/source pages
- full repo verification still at 100% backend/web coverage thresholds
- live stack proof using docker compose, migrations, setup script, source trigger, and smoke validation

## Risks And Honest Limits

- Real marketed opportunities still depend on at least one compliant listed source being live.
- Official/open planning datasets may remain supplemental rather than authority-of-record for some borough conclusions, which means manual review and abstain states must remain intact.
- Title/reference refresh at real London scale may require careful operator defaults and storage/runtime sizing.
- The opportunity queue may be sparse until both a real listed-source channel and enough authoritative planning/reference coverage are present.

## Implementation Units

1. Source legality and operator configuration
- add explicit real-source configuration path for compliant automated sources
- document what is and is not acceptable for launch

2. Official data remote refresh
- add remote-download capable refresh helpers for valuation/reference/planning families that can be automated truthfully

3. Queue automation chain
- auto-promote eligible clusters to sites
- auto-suggest scenarios after site build
- auto-build assessments for safe auto-confirmed scenarios

4. Web/admin readiness
- ensure all audited surfaces show live truth for the automated pipeline

5. Runtime proof
- run the full compose stack against real configured sources and verify that real data reaches frontend opportunities/review surfaces
