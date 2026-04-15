# London-First Land Intelligence Platform
## Controlling Implementation Specification (v1)

**Status:** build-ready controlling spec  
**As of:** 2026-04-15  
**Primary user:** internal land/planning analyst  
**Geographic scope:** Greater London only  
**Acquisition scope:** only land or land-like sites that are **currently listed for sale** in compliant source channels  
**Primary objective:** identify listed land with hidden planning upside, estimate the likelihood of **first-decision planning approval** for a defined proposal scenario, estimate the **post-permission value uplift**, and preserve an evidence trail that a human can audit and override

---

## 0. What this document is

This is the single implementation spec for v1.

It is deliberately opinionated. It makes stack, workflow, model, data, and operating decisions so that coding can start immediately. It is not a vision deck and it is not a generic AI/property platform spec.

This document also intentionally replaces several assumptions that are common in early planning-tech specs and that are not acceptable here:

1. **No parcel-only scores.** The system never scores a bare parcel or title without an explicit proposal scenario.
2. **No black-box scoring.** Every estimate must show evidence for, evidence against, evidence unknown, source links, and model/version metadata.
3. **No “absence means no issue”.** Missing data never proves absence of policy, absence of constraint, or absence of extant permission.
4. **No portal-scrape assumption.** Listing acquisition must be compliant with source terms or commercial arrangements.
5. **No probability-first build order.** The build starts with evidence ingestion, geometry, extant-permission logic, scenario normalization, and analyst review. The model comes later.
6. **No fake certainty.** The system must still estimate when it reasonably can, but it must label evidence quality, uncertainty, and manual-review requirements explicitly.

---

## 1. Product thesis

The platform exists to answer one commercial question:

> **Which currently listed London sites are being offered to the market without extant planning permission, but look capable of obtaining permission on first decision for a plausible residential-led proposal, and how much value uplift would that permission likely create?**

That breaks into two product functions.

### 1.1 Discovery and evidence assembly

For every relevant live listing, the system must:

- capture the listing and its documents as immutable snapshots
- determine whether the listing is actually a land/redevelopment target
- build or confirm a site geometry
- determine whether extant residential permission already exists
- assemble planning context:
  - site characteristics
  - borough and London-wide policy signals
  - nearby approvals/refusals
  - environmental/heritage/design constraints
  - brownfield / PiP / prior approval context
  - article 4 / permitted development context
  - local precedent and borough behavior
- preserve a source-backed evidence pack

### 1.2 Scenario-conditioned decision support

For every eligible site and scenario, the system must estimate:

1. **Planning probability:** the probability that a planning application matching the defined scenario would receive a **positive first substantive decision** from the relevant local planning authority.
2. **Post-permission economics:** the likely value of the site **with permission in place**, the uplift versus current acquisition basis, and the expected uplift once planning probability is considered.

The system is a decision-support tool for an analyst. It is not a fully autonomous land buyer.

---

## 2. Hard product rules

These rules are non-negotiable.

### 2.1 A score always belongs to a site + scenario + date

The system must never emit a generic “planning score” for a site without:

- `site_id`
- `scenario_id`
- `assessment_geom_hash`
- `as_of_date`
- `model_release_id`
- `source_snapshot_set`

### 2.2 Discovery is London-wide; speaking authority is borough-gated

Discovery can run across all Greater London from day one.

Probability and valuation outputs may be shown only for boroughs whose baseline packs, source coverage, and QA gates have been signed off. A site in an unsigned borough can still have an evidence pack and scenario workflow, but not a speaking score.

### 2.3 The assessed land unit is the site geometry, not a single title polygon

The system must support a **site geometry** that can be linked to one or more Land Registry titles.

This is a deliberate change from single-title-first designs. Listed sites often do not map cleanly to one open title polygon. V1 should therefore treat:

- the **assessment geometry** as the primary object of analysis
- title polygons as linked evidence, not the only legal/spatial unit

A site may still be blocked from scoring if the geometry is too weak, too ambiguous, or crosses local planning authority boundaries materially without analyst confirmation.

### 2.4 The system must estimate when reasonable, but must label uncertainty

The system should not default to refusal-to-score merely because data is imperfect.

Instead it must return one of:

- `ELIGIBILITY_FAIL`
- `ABSTAIN`
- `ESTIMATE_AVAILABLE`
- `ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED`
- `RANK_ONLY`

`ABSTAIN` is reserved for cases where mandatory prerequisites are missing or contradictory. Low evidence quality alone does **not** force abstention; it forces manual review and an explicit quality label.

### 2.5 LLMs are assistive only

LLMs may assist with:

- brochure/document summarization
- candidate extraction from text
- draft evidence summaries
- analyst-facing explanation drafting

LLMs may **not** be authoritative for:

- policy geometry
- extant permission determination
- final feature values used by the model, unless human-verified
- final score production logic

### 2.6 Economics never outrank planning state

A site with poor or uncertain planning prospects must not outrank a stronger planning case solely because the headline guide price looks cheap.

Ranking logic must use planning state first, economics second.

### 2.7 Every visible result must be replayable

Every final visible result must be reproducible from:

- frozen features
- frozen model/calibration release
- frozen source snapshot set
- frozen scenario parameters
- frozen geometry hash

---

## 3. V1 scope

### 3.1 In scope

- Greater London only
- currently listed land or land-like redevelopment opportunities only
- internal users only
- residential-led scenarios only
- analyst review workflow
- source-traceable outputs
- scenario-conditioned probability estimates
- post-permission valuation uplift ranges
- analyst override and audit trail
- calibration monitoring over time

### 3.2 Out of scope

- off-market sourcing
- nationwide coverage
- public SaaS product
- automated negotiation workflow
- legal title due diligence
- contamination / utilities / rights-of-way due diligence beyond what is already present in planning evidence
- fully automated parcel assembly
- development management after acquisition
- committee or appeal outcome prediction as a production feature
- commercial-only / logistics-only / industrial-only scenario families
- complex mixed-use towers
- schemes above 49 dwellings in v1

### 3.3 Target opportunity definition

A v1 target opportunity is:

- a live listing for sale
- in Greater London
- land or a land-like redevelopment site
- no extant residential planning permission, PiP, active residential prior approval, or equivalent order-based permission materially covering the assessment geometry
- able to support at least one enabled v1 scenario template
- supported by enough source coverage to build an auditable assessment

---

## 4. Deployment and stack decisions

## 4.1 Chosen stack

### Backend and processing
- **Python 3.12**
- **FastAPI** for API
- **SQLAlchemy 2 + Alembic**
- **psycopg 3**
- **Shapely / GeoPandas / pyogrio (worker image only)**
- **scikit-learn** for v1 model and calibration
- **PyMuPDF** for document text extraction
- **Playwright** for connectors that require browser rendering
- **httpx + BeautifulSoup** for normal HTTP connectors

### Database and storage
- **Supabase Postgres + PostGIS**
- **Supabase Storage** for immutable-by-convention raw snapshots, documents, and model artifacts
- **Supabase Auth** for analyst authentication and role bootstrap

### Frontend
- **Next.js + TypeScript**
- **Netlify** for hosting the internal web UI
- **MapLibre GL JS** for map rendering

### Job execution
- **Postgres-backed job table** with worker polling via `FOR UPDATE SKIP LOCKED`
- **APScheduler / cron** for recurring schedules

### Observability
- structured JSON logs
- Sentry
- Prometheus-compatible metrics endpoint on the API and worker

## 4.2 Why this stack is the right fit

This stack matches the stated constraint set:

- no AWS requirement
- simple operational model
- strong geospatial support
- maintainable Python-heavy backend
- low DevOps overhead
- direct SQL/PostGIS control rather than hidden no-code pipelines

Supabase is acceptable here because the product needs real PostgreSQL + PostGIS, durable storage, and simple auth more than it needs a complex cloud estate. Netlify is acceptable because the frontend is an internal Next.js app and all sensitive logic stays in the API. [^supabase-postgis] [^supabase-storage] [^supabase-pitr] [^netlify-next]

## 4.3 Physical architecture

```text
+-----------------------+          +------------------------------+
| Netlify               |          | Supabase                    |
| Next.js web           |  HTTPS   | Postgres + PostGIS         |
| Internal analyst UI   +--------->+ Storage + Auth             |
+-----------+-----------+          +------+-----------------------+
            |                             ^
            | HTTPS                       |
            v                             |
+-----------+-----------------------------+-----------------------+
| VPS (Docker Compose)                                           |
|                                                                |
|  +----------------+   +----------------+   +----------------+  |
|  | api            |   | worker         |   | scheduler      |  |
|  | FastAPI        |   | ETL / scoring  |   | recurring jobs |  |
|  +----------------+   +----------------+   +----------------+  |
|                                                                |
|  +----------------+                                            |
|  | nginx / caddy  |                                            |
|  +----------------+                                            |
+----------------------------------------------------------------+
```

## 4.4 What not to add in v1

Do **not** add the following in v1:

- Kubernetes
- event bus
- microservices by domain
- separate ML-serving infrastructure
- Elasticsearch/OpenSearch unless clearly needed later
- a vector DB
- a tile server unless bbox GeoJSON performance proves insufficient
- Redis unless the Postgres job queue demonstrably fails at pilot scale

---

## 5. Source strategy

## 5.1 Source classes

Every source-backed fact must carry a source class.

### A. Authoritative legal or spatial source
Use as source of truth for legal status or official geography.

Examples:
- borough planning register / approved feed
- borough policy GIS
- London-wide adopted policy GIS
- HM Land Registry open datasets
- Environment Agency statutory flood data
- adopted local plan / London Plan documents

### B. Official but incomplete / indicative source
Useful, but not sufficient by itself for a blocking legal conclusion.

Examples:
- Planning Data datasets marked incomplete/work in progress
- London-wide dashboards with data-quality caveats
- indicative policy map layers

### C. Market source
Commercial/listing source. Useful for current sale status, guide price, brochure claims, and market context. Never authoritative for planning status.

Examples:
- agent listing pages
- auction catalogues
- portal listing pages
- brochures

### D. Analyst-derived source
A structured fact created by an analyst from source materials.

Examples:
- manually drawn site polygon
- analyst-confirmed scenario
- analyst-curated borough rulepack

### E. Machine-derived assistive source
A candidate fact produced by extraction or ML tooling. Must not be treated as authoritative until validated.

Examples:
- brochure NLP extraction
- LLM-generated policy summary
- machine-generated geometry candidate

## 5.2 London v1 source families

| Domain | Primary v1 source | Role in system | Blocking rule |
|---|---|---|---|
| Live land listings | compliant source connectors (licensed portal feed if available, approved public pages, auction catalogues, manual URL intake) | discovery and market evidence | no connector may run without compliance mode set |
| London-wide planning application index | Planning London Datahub (PLD) | fast London-wide application index, comparable candidate pool, supplemental enrichment | not sole label authority for final scoring |
| Borough planning register / feed | borough-specific planning register or approved vendor feed | authoritative label and extant-permission source | mandatory for speaking boroughs |
| London-wide planning policy layers | GLA Planning DataMap + linked services | London-wide and borough-layer policy geometry discovery | use as geometry source only after baseline QA |
| Strategic policy text | London Plan 2021 | London-wide policy baseline | mandatory |
| Borough policy documents | borough local plan docs, neighbourhood plans, supplementary guidance where materially relied upon | borough baseline packs | mandatory for enabled borough/scenario |
| Title polygons | HM Land Registry INSPIRE open polygons | base title linkage and parcel evidence | indicative only; not legal parcel truth |
| Title upgrade path | HM Land Registry National Polygon Service (optional later) | improved title geometry / UPRN linkage | later upgrade if INSPIRE limitations harm ops |
| Flood | Environment Agency Flood Map for Planning | statutory flood constraint signal | mandatory |
| Environment / ecology | MAGIC and source-owner data where needed | constraint signal | mandatory where relevant to scenario |
| Brownfield / PiP | Planning Data + borough register/history | extant-permission and brownfield evidence | mandatory |
| Article 4 / TPO / conservation / listed buildings | Planning Data + borough / Historic England / borough GIS fallback | constraint / policy signal | borough fallback required if dataset incomplete for a critical conclusion |
| Market comparables | HMLR Price Paid Data + UKHPI + permissioned land listing comparables | value model | HMLR mandatory; permissioned listing comps optional but valuable |
| Appeals | Planning Inspectorate casework database | analyst evidence, later model expansion | optional in v1 scoring |

## 5.3 Critical v1 source facts

These facts drive the design and are treated as normative:

- The current Planning Data API provides over 100 planning and housing datasets through one interface, but the Planning Data **planning application** dataset currently carries an explicit warning that it is incomplete and not yet ready for use. [^planning-data-docs] [^planning-application-incomplete]
- The Planning London Datahub is a live, publicly accessible London-wide planning application/proposal database, but GLA dashboards note that incoming Datahub data is not fully quality-checked as received and may require amendment. Therefore PLD is useful as a London-wide index and comparable source, but borough planning registers remain the authority of record for labels and extant permission. [^pld-overview] [^pld-quality]
- Brownfield Part 1 does **not** itself mean permission in principle, while sites entered in Part 2 do receive permission in principle. [^brownfield-guidance]
- HM Land Registry INSPIRE polygons are an open subset of freehold registered property locations and are therefore helpful, but not a complete parcel cadastre. [^hmlr-inspire]
- Environment Agency flood-zone data is suitable only as an indication of flood risk area, not as a property-specific flood answer. [^ea-flood]
- Several Planning Data constraint datasets are explicitly incomplete or work in progress, including planning application, article 4 direction, conservation area, tree preservation zone, and listed building outline coverage. That means they can accelerate enrichment but cannot silently replace borough/source-owner checks where a conclusion is legally material. [^planning-application-incomplete] [^article4-incomplete] [^conservation-incomplete] [^tree-preservation-incomplete] [^listed-building-outline]

## 5.4 Listing acquisition policy

The product exists to find live listings, so listing acquisition is a first-class subsystem.

### Allowed acquisition modes

1. **Licensed feed connector**
   - preferred for large portals
   - highest operational stability
   - may require commercial agreement

2. **Compliant public-page connector**
   - approved per-domain after terms/robots/commercial review
   - snapshots HTML, PDF brochures, and visible facts

3. **Manual URL intake**
   - analyst pastes a listing URL
   - system snapshots and normalizes it
   - essential in v1

4. **CSV / email / broker drop**
   - manual import path for brokers or internal researchers

### Disallowed acquisition mode

- any automated connector that has not been marked `COMPLIANT_AUTOMATED` in `listing_source`

### Important rule

The platform does **not** assume that a broad portal can be scraped freely. That is a commercial/legal decision, not a coding shortcut.

## 5.5 Discovery universe versus opportunity universe

The system should maintain two related but distinct universes.

### Opportunity universe
Sites currently listed **without** extant permission and eligible for target acquisition.

### Comparable universe
Sites currently listed **with** permission, or historic permissioned land evidence, which are useful for valuation and market benchmarking.

This separation matters. Permissioned sites are not acquisition targets for the primary strategy, but they are valuable valuation comparables.

---

## 6. Core domain model

The product domain has six primary objects.

### 6.1 `listing_item`
A listing as seen from one external source.

Examples:
- a specific auction lot page
- a specific agent land page
- a portal listing row

### 6.2 `listing_cluster`
A set of source listings believed to represent the same marketed opportunity.

Examples:
- the same land plot on an agent site and on a portal
- the same lot mirrored across multiple pages

### 6.3 `site_candidate`
The assessed land object used by planning analysis.

A `site_candidate` is built from a confirmed geometry and linked evidence, not from one external listing row.

### 6.4 `site_scenario`
A structured hypothesis of what is being assessed.

Examples:
- 3 dwellings, full application
- 8 dwellings, full application
- 22 dwellings, outline application

### 6.5 `assessment_run`
One frozen evaluation of a site + scenario + date + model release.

### 6.6 `valuation_run`
One frozen economic evaluation tied to an assessment run and an assumptions set.

---

## 7. Site discovery and geometry

## 7.1 Why geometry is central

Everything in this system depends on having a usable site geometry:

- extant permission checks
- planning-history joins
- policy/constraint intersections
- comparable selection
- valuation assumptions
- auditability

Without usable geometry, the system cannot responsibly score.

## 7.2 Geometry sources and confidence ladder

Each site geometry must carry both a `geom_source_type` and a `geom_confidence`.

### Source types
- `SOURCE_POLYGON` — exact or near-exact polygon from source data
- `SOURCE_MAP_DIGITISED` — polygon digitized from listing/brochure map
- `TITLE_UNION` — polygon created from linked HMLR titles
- `ANALYST_DRAWN` — polygon drawn or corrected manually by analyst
- `APPROXIMATE_BBOX` — loose bounding geometry from a web map
- `POINT_ONLY` — only a point is known

### Confidence classes
- `HIGH`
- `MEDIUM`
- `LOW`
- `INSUFFICIENT`

### Probability speaking rule
Probability may be shown only when geometry confidence is:

- `HIGH`, or
- `MEDIUM`, or
- `LOW` **with** manual review completed

`POINT_ONLY` is never enough for speaking probability.

## 7.3 Geometry workflow

1. Connector ingests listing page and brochure.
2. System extracts any native coordinates or map references.
3. System attempts title matching and draft polygon generation.
4. Analyst confirms, edits, or redraws the site.
5. System freezes a geometry revision and hashes it.
6. All downstream analysis uses the frozen geometry revision.

## 7.4 Multi-title support

V1 must support one site geometry linked to multiple titles.

This is required because many marketed London opportunities span:

- small assembled plots
- rear-land fragments
- yard + building combinations
- garage courts with separate titles

### Scoring rule
A multi-title site is allowed **if**:

- the assessment geometry is clear
- the site lies materially within one local planning authority
- title linkage confidence is sufficient for audit

## 7.5 Multi-LPA rule

A site crossing local planning authority boundaries is high risk operationally.

### Rules
- If cross-LPA overlap is trivial (`<5%` of site area and `<100 sqm`), keep the majority LPA and flag.
- If overlap is material, manual clipping or analyst-confirmed geometry is required.
- No visible score is allowed until one controlling assessment geometry inside one LPA is frozen.

---

## 8. Eligibility and extant-permission logic

## 8.1 Eligibility states

Every site/scenario pair returns:

- `PASS`
- `FAIL`
- `OUT_OF_SCOPE`
- `ABSTAIN`

`ABSTAIN` is only for missing/contradictory prerequisites, not for “the score is inconvenient”.

## 8.2 Candidate screening rules

A discovered listing becomes a `site_candidate` only if all are true:

- live listing status indicates it is still on the market
- within Greater London
- appears to be land or a land-like redevelopment opportunity
- geometry is at least `APPROXIMATE_BBOX`
- not obviously outside residential-led v1 scope
- no immediate fatal source contradiction

## 8.3 What counts as extant permission for exclusion

A site is not a hidden-upside target if the assessment geometry is already materially covered by an active permission or equivalent residential right.

The exclusion set includes:

1. active **full residential planning permission**
2. active **outline residential planning permission**
3. active **permission in principle**
4. active linked **technical details consent**
5. active residential **prior approval / permitted development route** that would already enable the use/value change in question
6. active **order-based permissions** (for example local or neighbourhood order-based development rights) where materially applicable

### Important notes
- **Brownfield Part 1 is not enough to exclude.**
- **Brownfield Part 2 is enough to create PiP and therefore matters materially.**
- historic approvals that have expired or lapsed do **not** exclude, but they are important evidence
- a refusal does not exclude
- a withdrawn application does not exclude

## 8.4 Material overlap rule

For extant permission checks:

- `material_overlap = overlap_pct >= 10% OR overlap_sqm >= 100 OR permission materially controls access/frontage/core developable envelope`

### Outcomes
- active extant permission + material overlap -> `ELIGIBILITY_FAIL`
- active extant permission + non-material overlap -> `ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED`
- uncertain permission state because a required source family is missing -> `ABSTAIN`

## 8.5 Prior approval and permitted development rule

Residential prior approvals matter because they can already create much of the value change the platform is trying to find.

### V1 rule
For any borough/scenario where relevant residential prior approval coverage is incomplete or untrusted:

- visible probability must not speak automatically
- manual review is required
- if the gap is severe enough to invalidate the target definition, return `ABSTAIN`

The system must not silently assume “no prior approval found” means “no prior approval exists”.

## 8.6 Article 4 rule

Article 4 directions are not exclusionary in the same way as extant permission.

They are a planning-context fact that can:

- remove permitted development routes
- increase the need for full planning permission
- materially weaken or alter a scenario

They therefore influence eligibility, scenario framing, and score quality, but do not by themselves equal “permission exists”.

## 8.7 Listing claims are never authoritative for permission status

Examples of non-authoritative listing claims:

- “subject to planning”
- “development potential”
- “no planning history”
- “previously approved”
- “positive pre-app view”

These are market-source claims only.

They may trigger checks, but they must never replace register/source validation.

---

## 9. Scenario system

## 9.1 Principle

The model predicts the chance of approval for a **defined proposal scenario**, not for a bare site.

A site can have multiple plausible scenarios.

## 9.2 Enabled v1 scenario templates

V1 supports the following scenario templates.

| Template key | Description | Units | Route | Notes |
|---|---|---:|---|---|
| `resi_1_4_full` | small residential scheme | 1–4 | full | typically infill, side/rear land, garage court, or very small redevelopment |
| `resi_5_9_full` | small-medium residential scheme | 5–9 | full | typically small urban redevelopment or denser infill |
| `resi_10_49_outline` | medium residential scheme | 10–49 | outline by default | typically brownfield or surplus site redevelopment |

### Future templates
The architecture must support later addition of:
- mixed-use residential
- Class MA / prior approval families
- airspace
- student / co-living
- care / specialist housing
- larger major residential schemes

## 9.3 Scenario parameters

Every scenario must include at least:

- `template_key`
- `proposal_form`:
  - `INFILL`
  - `REDEVELOPMENT`
  - `BROWNFIELD_REUSE`
  - `BACKLAND`
  - `AIRSPACE` (future)
- `units_assumed`
- `route_assumed`
- `height_band_assumed`
- `net_developable_area_pct`
- `housing_mix_assumed`
- `parking_assumption`
- `affordable_housing_assumption`
- `access_assumption`
- `red_line_geom_hash`
- `scenario_source` (`AUTO`, `ANALYST`, `IMPORTED`)

## 9.4 Scenario generation modes

### Analyst-led
The analyst picks or edits the scenario manually.

### Auto-suggested
The system proposes 1–3 scenario hypotheses based on:

- site area
- geometry shape
- current use / listing clues
- surrounding built form
- PTAL
- nearby approved schemes
- borough rulepack constraints
- brownfield / redevelopment context

These are explicitly labelled as **hypotheses**, not facts.

## 9.5 Scenario normalization states

Every scenario must be in one of:

- `SUGGESTED`
- `AUTO_CONFIRMED`
- `ANALYST_CONFIRMED`
- `ANALYST_REQUIRED`
- `REJECTED`
- `OUT_OF_SCOPE`

### Speaking rule
No visible probability may be shown unless the scenario is:

- `AUTO_CONFIRMED`, or
- `ANALYST_CONFIRMED`

## 9.6 Auto-confirm rule

V1 may auto-confirm only when all are true:

- one scenario clearly dominates the heuristic candidates
- geometry confidence is at least `MEDIUM`
- no critical policy/source gaps exist
- units and route fall cleanly inside an enabled template
- nearest historical support is strong

Otherwise default to `ANALYST_REQUIRED`.

---

## 10. Borough baseline packs and rulepacks

## 10.1 Why baseline packs exist

This product cannot rely on free-form PDF reading at runtime for core planning logic.

Each speaking borough therefore needs a signed-off **baseline pack**.

## 10.2 What a borough baseline pack contains

A borough baseline pack is a versioned, signed-off set of:

- controlling policy documents for enabled templates
- policy geometry inventory and source links
- neighbourhood plan list where material
- borough-specific rule summary for enabled templates
- article 4 / conservation / heritage caveats
- CIL / affordable-housing / major-threshold assumptions for valuation
- known data quality gaps and workarounds
- source freshness baseline
- signoff metadata

## 10.3 What a borough rulepack contains

A borough rulepack is a normalized, machine-readable subset of the baseline pack. It should contain only facts needed repeatedly in scenario evaluation and valuation.

Examples:
- whether the borough has strong small-site intensification support in relevant contexts
- whether certain open-space designations behave as near-blockers
- affordable-housing trigger logic relevant to v1 templates
- borough CIL assumptions
- parking policy simplifications used in v1
- industrial land release caution flags
- conservation/heritage sensitivity multipliers

## 10.4 Rulepack principle

Rulepacks are **not** the law. They are normalized operational summaries tied back to source documents and geometry. Every rule must cite its source.

---

## 11. Evidence feature construction

## 11.1 Feature philosophy

Use explicit, versioned, interpretable features.

Do not use hidden embedding vectors or opaque LLM summaries as primary model inputs in v1.

## 11.2 Feature families

### A. Site geometry and morphology
- site area
- perimeter
- compactness
- frontage proxy if available
- corner-lot proxy if available
- existing building coverage proxy if available
- land-slope proxy (future)

### B. Location and access
- borough
- PTAL bucket
- distance to station
- distance to town centre proxy if available
- surrounding residential density proxy

### C. Planning history on site
- previous approvals
- previous refusals
- repeated application patterns
- historic density attempted
- recent withdrawals
- known pre-app reference if captured

### D. Nearby planning history
- approvals in 0–100m
- refusals in 0–100m
- approvals in 100–500m
- refusals in 100–500m
- same-template precedent density
- nearby committee-vs-delegated patterns where relevant

### E. Policy and designation context
- London Plan strategic context flags
- borough policy area intersections
- designated open space / MOL / Green Belt overlap
- industrial land / SIL / LSIS style constraints where available
- town centre / opportunity area / intensification area flags where available
- neighbourhood plan applicability

### F. Environmental and heritage context
- flood zone
- conservation area
- listed building proximity / overlap
- TPO / tree zone overlap
- ecology/protected area overlap
- archaeology flag where available

### G. Permission-state context
- brownfield Part 1 / Part 2 state
- PiP / TDC state
- prior approval / PD context
- article 4 context
- order-based permission context

### H. Borough / market context
- borough recent first-decision approval rate for same template
- borough decision time metrics
- borough housing-delivery / growth pressure proxies where configured
- local new-build sales evidence
- current asking price / basis completeness
- local price trajectory rebasing context

## 11.3 Point-in-time feature rule

All model features must be reconstructable **as of the historical assessment date** used in training and backtesting.

No feature may leak future information.

## 11.4 Feature provenance rule

Every final feature used by the model must preserve:

- source snapshot IDs
- raw asset IDs where relevant
- transform version
- any analyst overrides
- any missingness flags

---

## 12. Planning history and comparable retrieval

## 12.1 Planning history matching strategy

A planning application can be linked to a site in multiple ways:

- polygon intersects site
- point falls within site
- point within configured distance threshold
- title/address similarity
- brochure-referenced planning reference
- analyst-confirmed link

Each link must store:
- `match_method`
- `distance_m`
- `overlap_pct`
- `confidence`
- `manual_verified`

## 12.2 Local history retrieval windows

V1 default windows:

- **on-site:** intersects assessment geometry
- **adjacent:** 0–50m
- **local precedent:** 50–250m
- **local context:** 250–500m
- **borough-wide support pool:** same borough
- **London-wide support pool:** fallback

These windows are configurable per template.

## 12.3 Comparable case selection

Comparables are explanation artifacts, not a substitute model.

A comparable set should aim to return:
- 3 approved cases
- 3 refused cases

using similarity on:
- template
- proposal form
- unit count
- site area
- PTAL
- designation profile
- borough or archetype
- time recency

If the borough has weak support, fallback to:
1. same borough -> same template
2. London-wide -> same template
3. archetype fallback -> same template

Every fallback must be visible to the analyst.

---

## 13. Probability engine

## 13.1 Prediction target

V1 planning probability target:

> **Probability that the relevant local planning authority will issue a positive first substantive decision for the confirmed site scenario within 18 months of application validation, without needing an appeal outcome to become positive.**

### Positive labels
- approve
- conditional approve
- resolve to grant / minded to grant where treated operationally as the first positive decision and documented as such

### Negative labels
- refuse

### Excluded / censored labels
- withdrawn
- invalid
- undetermined / still pending beyond label window
- duplicate / administrative records
- appeal-only outcomes
- non-relevant application types

## 13.2 Model choice

### Production champion model in v1
**Regularized logistic regression** on explicit, versioned, interpretable features, with per-template calibration.

This is the production choice for v1 because it is:

- easy to audit
- easy to replay
- simple to explain locally
- robust with moderate pilot data
- straightforward to monitor for calibration drift
- operationally lightweight

### Optional offline challenger
One offline challenger may be maintained for research only:
- Explainable Boosting Machine, or
- LightGBM with strict feature governance and post-hoc explanation

The challenger is not required to ship v1.

## 13.3 Feature treatment

- categorical features: one-hot encode
- numeric features: log/ratio transforms and/or stable bins where appropriate
- missingness: explicit indicator columns
- interactions: whitelist only, versioned explicitly
- no target encoding in v1 production
- no free-text embeddings in v1 production score path

## 13.4 Calibration

Use one calibration artifact per template family, with borough/archetype overrides only if validation proves they improve reliability materially.

Allowed methods:
- isotonic calibration
- Platt / logistic calibration

Store calibration as a versioned artifact.

## 13.5 Output fields

The probability engine returns:

- `approval_probability_raw`
- `approval_probability_display` (rounded to nearest 5 percentage points)
- `estimate_quality` (`HIGH`, `MEDIUM`, `LOW`)
- `manual_review_required`
- `support_counts`
- `ood_status`
- `model_release_id`
- `target_definition`
- `positive_drivers`
- `negative_drivers`
- `unknowns`
- `comparable_set_id`

## 13.6 Display policy

### Internal raw output
Raw probability retained in ledger and admin views.

### Analyst display
Rounded to nearest 5 percentage points.

### Why
This prevents false precision while still giving a usable estimate.

## 13.7 Estimate-quality policy

The system must estimate quality separately from the probability itself.

### Quality dimensions
- `source_coverage_quality`
- `geometry_quality`
- `support_quality`
- `ood_quality`
- `scenario_quality`

### Final estimate quality
- `HIGH`
- `MEDIUM`
- `LOW`

A low-quality estimate can still exist, but must:
- show warning state
- force manual review
- not auto-promote into top ranking queues

## 13.8 Out-of-distribution rule

The model must compute a simple OOD score per assessment, using:
- distance to training support in feature space
- same-template support counts
- same-borough support counts

If OOD exceeds threshold:
- estimate may still exist
- quality becomes `LOW`
- manual review becomes mandatory
- auto-priority ranking is disabled

## 13.9 Explanation requirements

For every speaking probability, return:

- plain-English target definition
- top positive drivers
- top negative drivers
- unknowns / missing evidence
- comparable approved cases
- comparable refused cases
- source freshness summary
- model/calibration release
- evidence item links

## 13.10 What the probability engine must not use

Do not use any feature unavailable before or at application framing time, such as:
- officer recommendation
- committee agenda outcome
- final consultation counts after submission if not part of the intended pre-application evidence frame
- appeal outcome
- post-decision events

---

## 14. Valuation and uplift engine

## 14.1 Valuation objective

The system is not estimating end-development profit for a housebuilder. It is estimating the likely **site value with permission in place** and the uplift from buying the site before permission.

## 14.2 Primary valuation outputs

For every assessment where economics can be run, return:

- `post_permission_value_low`
- `post_permission_value_mid`
- `post_permission_value_high`
- `uplift_low`
- `uplift_mid`
- `uplift_high`
- `expected_uplift_mid = approval_probability_raw * uplift_mid`
- `valuation_quality`
- `manual_review_required`

## 14.3 Acquisition basis

Uplift must always be measured against a declared acquisition basis.

Allowed basis types:
- `ASKING_PRICE`
- `GUIDE_PRICE`
- `POA_ANALYST_INPUT`
- `ANALYST_TARGET_PRICE`

If no acquisition basis exists:
- still compute post-permission value range
- set uplift fields to `null`
- mark valuation quality low unless later completed

## 14.4 V1 valuation method

V1 uses a **residual-land-value primary method** with **market sense-checks**.

### Method A — residual land value (primary)
1. start from scenario-defined unit count and mix
2. derive assumed NSA / GIA by template defaults and analyst edits
3. estimate local sales values using market evidence
4. calculate gross development value (GDV)
5. deduct:
   - build cost
   - externals
   - professional fees
   - planning / surveys / legal allowance
   - contingency
   - finance
   - developer margin
   - CIL / Mayoral CIL / borough assumptions
   - affordable housing / policy burden assumptions where relevant
6. output residual land value range

### Method B — market sense-check (secondary)
Use:
- current and historic permissioned land listing comparables
- auction evidence where available
- local market norms by site size / units / borough
- analyst benchmarks

If Methods A and B diverge materially:
- widen the range
- downgrade valuation quality
- require manual review

## 14.5 Market sources for valuation

### Mandatory official source
- HMLR Price Paid Data for sold prices
- UK HPI for rebasing older evidence

### Valuable internal/commercial comparables
- permissioned land listings in the comparable universe
- auction guide/result evidence
- analyst-maintained benchmark tables

## 14.6 Assumption governance

All valuation assumptions must live in a versioned `valuation_assumption_set` table.

They must include:
- build cost library version
- standard unit sizes by template
- fees / contingency / finance assumptions
- developer margin assumptions
- CIL assumptions
- affordable housing burden assumptions
- rebasing logic

Analysts may override assumptions case-by-case, but overrides must be auditable.

## 14.7 Valuation-quality policy

Valuation quality must be scored separately from planning probability.

Example factors:
- asking/guide price exists
- sales comp coverage is adequate
- permissioned land comp coverage is adequate
- CIL/affordable assumptions are known
- scenario mix and area assumptions are stable

### Output class
- `HIGH`
- `MEDIUM`
- `LOW`

## 14.8 Ranking use of economics

The primary ranking metrics are:

1. planning state
2. approval probability band
3. expected uplift
4. valuation quality
5. listing urgency

Economics may break ties within a planning band. It must not leapfrog a materially better planning case.

---

## 15. Evidence trail and explainability

## 15.1 Required evidence sections

Every assessment page must show:

1. **Scenario statement**
   - what exactly is being assessed

2. **Eligibility panel**
   - extant permission result
   - scope result
   - geometry confidence
   - borough enablement state

3. **Supportive evidence**
   - factors that strengthen permission likelihood

4. **Weakening evidence**
   - factors that weaken permission likelihood

5. **Unknowns / gaps**
   - what is missing or uncertain

6. **Comparable cases**
   - approvals and refusals

7. **Policy and constraint sources**
   - source links and raw docs

8. **Probability summary**
   - rounded output
   - quality labels
   - target definition

9. **Valuation summary**
   - range
   - basis
   - quality label

10. **Audit and versioning**
   - model release
   - source snapshot set
   - assessment ledger ID
   - overrides

## 15.2 Evidence item structure

Every evidence item should contain:

- `polarity` (`FOR`, `AGAINST`, `UNKNOWN`)
- `claim_text`
- `topic`
- `importance`
- `source_class`
- `source_label`
- `source_url`
- `source_snapshot_id`
- `raw_asset_id`
- `excerpt_text` or record reference
- `verified_status`

## 15.3 Why and why not output

The analyst should always be able to answer:

- why did this score well?
- why did this score badly?
- what facts is that based on?
- what is unknown?
- what could change the result?
- which assumptions were analyst-entered rather than source-derived?

---

## 16. Result states and review policy

## 16.1 Orthogonal status model

Use separate statuses rather than one overloaded status.

### A. Eligibility status
- `PASS`
- `FAIL`
- `OUT_OF_SCOPE`
- `ABSTAIN`

### B. Estimate status
- `NONE`
- `ESTIMATE_AVAILABLE`
- `ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED`
- `RANK_ONLY`

### C. Review status
- `NOT_REQUIRED`
- `REQUIRED`
- `COMPLETED`

## 16.2 Default visible policy

Default analyst-visible policy for v1:

- show estimate if eligibility passes and mandatory prerequisites exist
- round probability to nearest 5%
- show quality labels prominently
- require manual review for low-quality or OOD cases
- suppress auto-priority promotion if manual review required

## 16.3 Hard abstain conditions

Return `ABSTAIN` when any is true:

- geometry is `POINT_ONLY` or otherwise insufficient
- extant permission state is unresolved because a mandatory source family is missing
- borough baseline pack is not signed off for the scenario
- source contradiction is severe (for example one source indicates active permission and another indicates no permission, with no resolution)
- the site lies materially across LPAs without confirmed clipped geometry

## 16.4 Manual review triggers

Manual review is required when any is true:

- geometry confidence is `LOW`
- extant permission overlap is non-zero but not clearly material
- prior approval coverage is incomplete
- article 4 or policy geometry is incomplete for a critical conclusion
- OOD is high
- support counts are weak
- valuation quality is low
- asking price is missing
- scenario was auto-suggested but not stable enough to auto-confirm

---

## 17. Data model

This section defines the minimum canonical schema.

## 17.1 Provenance and source tables

### `source_snapshot`
Purpose: immutable record of one source acquisition event or batch.

Required columns:
- `id`
- `source_family`
- `source_name`
- `source_uri`
- `acquired_at`
- `effective_from`
- `effective_to`
- `schema_hash`
- `content_hash`
- `coverage_note`
- `freshness_status`
- `manifest_json`

### `raw_asset`
Purpose: immutable stored object.

Required columns:
- `id`
- `source_snapshot_id`
- `asset_type`
- `original_url`
- `storage_path`
- `mime_type`
- `content_sha256`
- `size_bytes`
- `fetched_at`

### `source_coverage_snapshot`
Purpose: coverage and gap record per source family and borough.

Required columns:
- `id`
- `borough_id`
- `source_family`
- `coverage_geom_27700`
- `coverage_status`
- `gap_reason`
- `captured_at`

## 17.2 Listing tables

### `listing_source`
Required columns:
- `id`
- `name`
- `connector_type`
- `compliance_mode`
- `refresh_policy_json`
- `active`

### `listing_item`
Required columns:
- `id`
- `source_id`
- `source_listing_id`
- `canonical_url`
- `listing_type`
- `first_seen_at`
- `last_seen_at`
- `latest_status`
- `current_snapshot_id`

### `listing_snapshot`
Required columns:
- `id`
- `listing_item_id`
- `observed_at`
- `headline`
- `description_text`
- `guide_price_gbp`
- `price_basis_type`
- `status`
- `auction_date`
- `address_text`
- `lat`
- `lon`
- `brochure_asset_id`
- `map_asset_id`
- `raw_record_json`

### `listing_document`
Required columns:
- `id`
- `listing_item_id`
- `asset_id`
- `doc_type`
- `page_count`
- `extraction_status`
- `extracted_text`

### `listing_cluster`
Required columns:
- `id`
- `cluster_key`
- `cluster_status`
- `created_at`

### `listing_cluster_member`
Required columns:
- `id`
- `listing_cluster_id`
- `listing_item_id`
- `confidence`
- `created_at`

## 17.3 Site tables

### `site_candidate`
Required columns:
- `id`
- `listing_cluster_id`
- `display_name`
- `borough_id`
- `geom_27700`
- `geom_4326`
- `geom_hash`
- `geom_source_type`
- `geom_confidence`
- `site_area_sqm`
- `current_listing_id`
- `current_price_gbp`
- `current_price_basis_type`
- `site_status`

### `site_geometry_revision`
Required columns:
- `id`
- `site_id`
- `geom_27700`
- `geom_hash`
- `source_type`
- `confidence`
- `reason`
- `created_by`
- `created_at`
- `raw_asset_id`

### `site_title_link`
Required columns:
- `id`
- `site_id`
- `title_number`
- `source_snapshot_id`
- `overlap_pct`
- `overlap_sqm`
- `confidence`

### `site_lpa_link`
Required columns:
- `id`
- `site_id`
- `lpa_id`
- `overlap_pct`
- `overlap_sqm`

### `site_market_event`
Required columns:
- `id`
- `site_id`
- `event_type`
- `event_at`
- `price_gbp`
- `basis_type`
- `listing_item_id`
- `notes`

## 17.4 Planning and policy tables

### `planning_application`
Required columns:
- `id`
- `borough_id`
- `source_system`
- `external_ref`
- `application_type`
- `proposal_description`
- `valid_date`
- `decision_date`
- `decision`
- `decision_type`
- `status`
- `route_normalized`
- `units_proposed`
- `site_geom_27700`
- `site_point_27700`
- `source_priority`
- `raw_record_json`

### `planning_application_document`
Required columns:
- `id`
- `planning_application_id`
- `asset_id`
- `doc_type`
- `doc_url`

### `site_planning_link`
Required columns:
- `id`
- `site_id`
- `planning_application_id`
- `link_type`
- `distance_m`
- `overlap_pct`
- `match_confidence`
- `manual_verified`

### `brownfield_site_state`
Required columns:
- `id`
- `borough_id`
- `external_ref`
- `geom_27700`
- `part`
- `pip_status`
- `tdc_status`
- `effective_from`
- `effective_to`
- `raw_record_id`

### `policy_area`
Required columns:
- `id`
- `borough_id`
- `policy_family`
- `policy_code`
- `name`
- `geom_27700`
- `legal_effective_from`
- `legal_effective_to`
- `source_snapshot_id`
- `source_class`

### `planning_constraint_feature`
Required columns:
- `id`
- `feature_family`
- `feature_subtype`
- `authority_level`
- `geom_27700`
- `legal_status`
- `effective_from`
- `effective_to`
- `source_snapshot_id`

### `site_policy_fact`
Required columns:
- `id`
- `site_id`
- `policy_area_id`
- `relation_type`
- `overlap_pct`
- `distance_m`
- `importance`

### `site_constraint_fact`
Required columns:
- `id`
- `site_id`
- `constraint_feature_id`
- `overlap_pct`
- `distance_m`
- `severity`

### `borough_baseline_pack`
Required columns:
- `id`
- `borough_id`
- `version`
- `status`
- `signed_off_by`
- `signed_off_at`
- `pack_json`

### `borough_rulepack`
Required columns:
- `id`
- `borough_baseline_pack_id`
- `template_key`
- `rule_json`
- `effective_from`
- `effective_to`

## 17.5 Scenario, assessment, and valuation tables

### `scenario_template`
Required columns:
- `key`
- `version`
- `enabled`
- `config_json`

### `site_scenario`
Required columns:
- `id`
- `site_id`
- `template_key`
- `proposal_form`
- `units_assumed`
- `route_assumed`
- `height_band_assumed`
- `net_developable_area_pct`
- `housing_mix_assumed_json`
- `parking_assumption`
- `affordable_housing_assumption`
- `access_assumption`
- `red_line_geom_hash`
- `scenario_source`
- `status`
- `supersedes_id`

### `scenario_review`
Required columns:
- `id`
- `scenario_id`
- `review_status`
- `review_notes`
- `reviewed_by`
- `reviewed_at`

### `assessment_run`
Required columns:
- `id`
- `site_id`
- `scenario_id`
- `as_of_date`
- `state`
- `idempotency_key`
- `requested_by`
- `started_at`
- `finished_at`

### `assessment_feature_snapshot`
Required columns:
- `id`
- `assessment_run_id`
- `feature_version`
- `feature_hash`
- `feature_json`
- `coverage_json`

### `model_release`
Required columns:
- `id`
- `template_key`
- `version`
- `artifact_path`
- `calibration_path`
- `metrics_json`
- `train_window_start`
- `train_window_end`
- `activated_at`
- `retired_at`

### `assessment_result`
Required columns:
- `id`
- `assessment_run_id`
- `model_release_id`
- `eligibility_status`
- `estimate_status`
- `review_status`
- `approval_probability_raw`
- `approval_probability_display`
- `estimate_quality`
- `source_coverage_quality`
- `geometry_quality`
- `support_quality`
- `ood_status`
- `manual_review_required`
- `result_json`
- `published_at`

### `comparable_case_set`
Required columns:
- `id`
- `assessment_run_id`
- `strategy`
- `same_borough_count`
- `london_count`
- `approved_count`
- `refused_count`

### `comparable_case_member`
Required columns:
- `id`
- `comparable_case_set_id`
- `planning_application_id`
- `similarity_score`
- `outcome`
- `rank`

### `evidence_item`
Required columns:
- `id`
- `assessment_run_id`
- `polarity`
- `topic`
- `claim_text`
- `importance`
- `source_class`
- `source_label`
- `source_url`
- `source_snapshot_id`
- `raw_asset_id`
- `excerpt_text`
- `verified_status`

### `valuation_assumption_set`
Required columns:
- `id`
- `version`
- `cost_json`
- `policy_burden_json`
- `discount_json`
- `effective_from`

### `valuation_run`
Required columns:
- `id`
- `assessment_run_id`
- `valuation_assumption_set_id`
- `state`
- `created_at`

### `valuation_result`
Required columns:
- `id`
- `valuation_run_id`
- `post_permission_value_low`
- `post_permission_value_mid`
- `post_permission_value_high`
- `uplift_low`
- `uplift_mid`
- `uplift_high`
- `expected_uplift_mid`
- `valuation_quality`
- `manual_review_required`
- `basis_json`

### `prediction_ledger`
Required columns:
- `id`
- `assessment_run_id`
- `site_geom_hash`
- `feature_hash`
- `model_release_id`
- `calibration_hash`
- `source_snapshot_ids_json`
- `raw_asset_ids_json`
- `result_payload_hash`
- `response_json`
- `created_at`

### `analyst_override`
Required columns:
- `id`
- `assessment_run_id`
- `override_type`
- `field_name`
- `old_value_json`
- `new_value_json`
- `reason`
- `created_by`
- `created_at`

### `audit_event`
Required columns:
- `id`
- `actor_user_id`
- `action`
- `entity_type`
- `entity_id`
- `before_json`
- `after_json`
- `created_at`

### `job_run`
Required columns:
- `id`
- `job_type`
- `payload_json`
- `status`
- `attempts`
- `run_at`
- `locked_at`
- `worker_id`
- `error_text`

## 17.6 Required indexes

At minimum:

- `GIST` on every `geom_27700`
- `BTREE` on `borough_id`, `external_ref`, `canonical_url`, `status`, `valid_date`, `decision_date`
- `GIN` trigram or FTS index on listing headlines/descriptions and application descriptions
- unique index on `assessment_run.idempotency_key`
- unique index on `listing_item(source_id, source_listing_id)`
- unique index on `model_release(template_key, version)`

## 17.7 Spatial rule

All canonical spatial operations must run in **EPSG:27700**.

Store `EPSG:4326` only for display/export.

---

## 18. API surface

The API should stay small and boring.

## 18.1 Discovery endpoints

### `POST /api/listings/intake/url`
Snapshot and normalize a manual URL.

### `POST /api/listings/connectors/{source_key}/run`
Run an approved connector.

### `GET /api/listings`
List raw or clustered listings with filters:
- borough
- live status
- source
- price range
- listing type
- permission-state flag
- review state

### `GET /api/listings/{listing_id}`
Return listing detail, snapshots, and extracted metadata.

## 18.2 Site endpoints

### `POST /api/sites/from-cluster/{cluster_id}`
Create or refresh a `site_candidate`.

### `GET /api/sites`
Map/list search over confirmed sites.

### `GET /api/sites/{site_id}`
Return site detail, geometry, planning context summary, listing summary.

### `POST /api/sites/{site_id}/geometry`
Create a new geometry revision.

### `POST /api/sites/{site_id}/extant-permission-check`
Re-run permission-state screening.

## 18.3 Scenario endpoints

### `POST /api/sites/{site_id}/scenarios/suggest`
Generate scenario hypotheses.

### `POST /api/scenarios/{scenario_id}/confirm`
Confirm or edit a scenario.

### `GET /api/scenarios/{scenario_id}`
Return scenario detail and assumptions.

## 18.4 Assessment endpoints

### `POST /api/assessments`
Create an assessment run.

Request body:
```json
{
  "site_id": "uuid",
  "scenario_id": "uuid",
  "as_of_date": "2026-04-15"
}
```

### `GET /api/assessments/{assessment_id}`
Return frozen result, evidence, comparables, and valuation.

### `POST /api/assessments/{assessment_id}/override`
Create analyst override.

## 18.5 Ranking endpoints

### `GET /api/opportunities`
Return ranked opportunity list with filters:
- borough
- probability band
- valuation quality
- manual review required
- auction deadline window
- price range

### `GET /api/opportunities/{site_id}`
Return latest ranking-relevant result for a site.

## 18.6 Admin / health endpoints

### `GET /api/health/data`
Source freshness, coverage gaps, failing boroughs.

### `GET /api/health/model`
Model release, calibration metrics, drift signals.

### `GET /api/admin/jobs`
Job queue state.

### `GET /api/admin/source-snapshots`
Source snapshot history and manifests.

## 18.7 Canonical assessment response shape

```json
{
  "assessment_id": "uuid",
  "site": {
    "site_id": "uuid",
    "display_name": "Garage Court off Example Road",
    "borough": "London Borough of Example",
    "site_area_sqm": 612,
    "geom_confidence": "MEDIUM"
  },
  "scenario": {
    "scenario_id": "uuid",
    "template_key": "resi_5_9_full",
    "proposal_form": "REDEVELOPMENT",
    "units_assumed": 7,
    "route_assumed": "FULL",
    "status": "ANALYST_CONFIRMED"
  },
  "eligibility": {
    "status": "PASS",
    "extant_permission_state": "NO_ACTIVE_PERMISSION_FOUND",
    "notes": []
  },
  "planning_probability": {
    "estimate_status": "ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED",
    "raw_probability": 0.67,
    "display_probability": "65%",
    "estimate_quality": "MEDIUM",
    "manual_review_required": true,
    "target_definition": "positive first substantive decision within 18 months"
  },
  "valuation": {
    "post_permission_value_low": 1250000,
    "post_permission_value_mid": 1450000,
    "post_permission_value_high": 1625000,
    "uplift_low": 350000,
    "uplift_mid": 550000,
    "uplift_high": 725000,
    "expected_uplift_mid": 368500,
    "valuation_quality": "LOW"
  },
  "evidence": {
    "for": [],
    "against": [],
    "unknown": []
  },
  "comparables": {
    "approved": [],
    "refused": []
  },
  "audit": {
    "model_release_id": "uuid",
    "prediction_ledger_id": "uuid",
    "source_snapshot_ids": ["uuid", "uuid"]
  }
}
```

---

## 19. Frontend requirements

## 19.1 Pages

### A. Discovery map / list
Purpose:
- browse all current site candidates
- filter by borough, status, price, scenario availability, review state

### B. Site detail
Purpose:
- listing summary
- geometry editor
- permission-state panel
- planning context map
- raw source docs

### C. Scenario editor
Purpose:
- view suggested scenarios
- edit parameters
- confirm scenario
- compare multiple scenarios for one site

### D. Assessment view
Purpose:
- planning probability
- valuation range
- evidence for/against/unknown
- comparables
- source list
- overrides

### E. Review queue
Purpose:
- manual-review-required cases
- recent changed cases
- borough/source-failing cases

### F. Data health dashboard
Purpose:
- source freshness
- connector failures
- borough coverage gaps
- model release health

## 19.2 UX rules

- never hide a material warning
- show estimate quality separately from probability
- use map layers for policy and planning history, but never imply map geometry is authoritative if marked indicative
- every key evidence item must be clickable back to the raw source
- always show the scenario being scored in headline form

---

## 20. Jobs, pipelines, and refresh cadences

## 20.1 Job system

Use a Postgres-backed `job_run` table with worker polling.

Required fields:
- `status`: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `DEAD`
- `attempts`
- `next_run_at`
- `locked_at`
- `worker_id`

## 20.2 Recurring jobs

### Listing refresh
- active sources: every 6 hours
- lower-priority sources: every 24 hours
- manual URL intake: immediate

### Planning index refresh
- PLD sync: daily
- borough register delta sync: daily or more frequently where available

### Constraint/policy refresh
- Planning Data and London-wide layers: daily/weekly depending source
- HMLR INSPIRE: monthly
- policy baseline and borough GIS checks: weekly metadata check, full update when changed

### Model/monitoring refresh
- calibration/drift reporting: monthly
- shadow replay / QA batch: weekly
- opportunity ranking snapshot: nightly

## 20.3 Snapshot rule

Every connector run must create:
- one `source_snapshot`
- one or more `raw_asset` rows
- coverage note
- parse status

No in-place overwrite.

---

## 21. Security, access, and audit

## 21.1 Roles

### `analyst`
- review sites
- edit geometry
- confirm scenarios
- run assessments
- create valuation overrides

### `reviewer`
- all analyst rights
- sign off cases
- resolve manual-review queue
- approve model visibility for limited pilot

### `admin`
- source signoff
- borough baseline signoff
- model release activation
- user role changes
- system settings

## 21.2 Authentication

Use Supabase Auth for v1:
- email magic link and/or Google sign-in
- all authorization enforced again in API by role table

## 21.3 Secrets

- no production secrets in git
- Netlify env vars for frontend public config only
- VPS env vars or Docker secrets for backend
- Supabase credentials scoped per environment

## 21.4 Audit requirements

Audit all of:
- geometry changes
- scenario confirmations
- assessment runs
- overrides
- borough baseline activations
- model release activations
- source compliance-mode changes

---

## 22. Monitoring and quality control

## 22.1 Data-health metrics

Track:
- source freshness by family and borough
- connector failure rate
- listing parse success rate
- geometry-confidence distribution
- extant-permission unresolved rate
- borough baseline coverage

## 22.2 Model-health metrics

Track monthly:
- calibration by probability band
- Brier score
- log loss
- manual-review agreement by band
- false-positive reviewer rate
- abstain rate
- OOD rate
- template-level performance

## 22.3 Economic-health metrics

Track:
- uplift null rate
- asking-price missing rate
- valuation-quality distribution
- realized acquisition/sale backtests where actual data is later available

## 22.4 Incident triggers

Trigger incident review when:
- source freshness breach affects a speaking borough
- borough baseline pack becomes stale or invalid
- extant-permission false-negative is discovered
- visible results fail replay
- model artifact hash mismatch occurs
- connector compliance mode is bypassed
- severe reviewer false-positive rate breaches threshold

---

## 23. Ranking policy

## 23.1 Ranking objective

The ranked opportunity list should help an analyst decide where to spend time first.

It is not an autonomous buy list.

## 23.2 Ranking formula

Use a simple, interpretable two-stage ranking.

### Stage 1: planning gate and band
Assign:
- `Band A`: probability >= 0.70 and estimate quality >= MEDIUM and no manual review required
- `Band B`: probability 0.55–0.70 or manual review required
- `Band C`: probability 0.40–0.55
- `Band D`: probability < 0.40
- `Hold`: `ABSTAIN`, `FAIL`, or `OUT_OF_SCOPE`

### Stage 2: economics and urgency inside band
Rank within band by:
1. `expected_uplift_mid`
2. `valuation_quality`
3. `auction deadline / urgency`
4. `asking price presence`
5. `same-borough support count`

## 23.3 Why this ranking policy

It preserves a core product rule:
- planning credibility comes first
- economics refines prioritization
- low-quality estimates do not quietly dominate the queue

---

## 24. Testing and validation

## 24.1 Unit tests

Cover:
- connector parsers
- extant-permission logic
- scenario normalization
- feature derivation transforms
- valuation formulas
- API serializers
- audit logging

## 24.2 Integration tests

Cover:
- source snapshot -> parse -> site creation
- site -> scenario -> assessment run
- assessment replay from frozen snapshots
- override flow
- ranking refresh

## 24.3 Geospatial tests

Cover:
- geometry validity repair
- LPA intersection
- overlap thresholds
- title linkage behavior
- policy and constraint joins

## 24.4 Historical replay tests

For a fixed historical batch:
- recompute features and score
- verify ledger hash stability
- verify explanation payload stability except allowed text formatting differences

## 24.5 Gold-set review

Build a manually adjudicated gold set of historical London cases for each enabled template.

Required fields:
- scenario family
- site geometry confidence
- positive/negative label confirmation
- extant-permission check outcome
- notable policy issues

## 24.6 Validation thresholds before visible probability

Minimum expectations before broader internal use:
- calibration acceptable by band
- no major source leakage
- extant-permission false-negative rate low enough to trust
- borough baseline packs complete for speaking boroughs
- replay stability proven
- explanation completeness > 95% on test batch

---

## 25. Build order for Codex

This is the recommended implementation order. Do not start with the model.

## Phase 0 — repo, environments, and schema skeleton
**Goal:** make the project runnable end to end with no business intelligence yet.

Deliver:
- monorepo scaffold
- Dockerfiles
- Docker Compose for VPS
- Supabase project bootstrap
- Netlify project bootstrap
- Alembic migrations
- auth and role tables
- `source_snapshot`, `raw_asset`, `job_run`, `audit_event`

Exit criteria:
- API, worker, scheduler, and web all boot
- migrations run cleanly
- a manual URL can be posted and a raw snapshot stored

## Phase 1 — listing ingestion and clustering
**Goal:** create the live listings layer.

Deliver:
- approved connector framework
- manual URL intake
- HTML/PDF snapshotting
- listing parsing
- listing dedupe / clustering
- listing search UI

Exit criteria:
- system can ingest at least 3 different listing source types
- listing snapshots are immutable
- duplicate listings cluster reliably on a sample set

## Phase 2 — site geometry and basic map
**Goal:** turn listings into auditable sites.

Deliver:
- site creation from clusters
- draft geometry creation
- geometry editor in UI
- HMLR title linkage
- LPA linkage
- geometry confidence framework

Exit criteria:
- analysts can confirm or edit a site polygon
- title linkage and borough assignment are visible
- no scoring yet

## Phase 3 — planning context and evidence pack
**Goal:** make the platform useful before ML.

Deliver:
- PLD ingestion
- borough planning-register ingestion for initial pilot boroughs
- Planning Data constraints ingestion
- London DataMap / borough policy-layer ingestion
- flood / heritage / article 4 / brownfield enrichment
- evidence-only site detail page
- extant-permission engine

Exit criteria:
- site detail shows evidence for/against/unknown
- extant permission is screened
- borough baseline pack structure exists
- still no visible probability

## Phase 4 — scenario engine
**Goal:** structured planning evaluation.

Deliver:
- scenario templates
- auto-suggestion heuristics
- scenario editor
- scenario confirmation workflow
- borough rulepacks
- frozen assessment geometry per scenario

Exit criteria:
- analysts can confirm scenarios end to end
- evidence pack becomes scenario-conditioned
- probability still hidden

## Phase 5 — historical labels and feature snapshots
**Goal:** make training data defensible.

Deliver:
- historical London planning application normalization
- label pipeline
- point-in-time feature reconstruction
- gold-set review workflow
- comparable-case retrieval
- prediction ledger

Exit criteria:
- reproducible historical feature snapshots
- gold set built for enabled templates
- same historical assessment can be replayed exactly

## Phase 6 — planning probability model
**Goal:** calibrated, explainable v1 scoring.

Deliver:
- logistic-regression champion
- calibration pipeline
- OOD logic
- estimate-quality logic
- explanation generator
- hidden-score mode in UI

Exit criteria:
- hidden/shadow results available
- validation thresholds pass
- manual-review rules work

## Phase 7 — valuation and ranking
**Goal:** turn planning support into acquisition prioritization.

Deliver:
- valuation assumptions tables
- residual land value engine
- market sense-check logic
- uplift calculation
- opportunity ranking view

Exit criteria:
- ranked site list exists
- economics never outrank planning band
- asking-price missing cases handled correctly

## Phase 8 — override, monitoring, and controlled visibility
**Goal:** safe internal usage.

Deliver:
- overrides UI
- data health dashboard
- model health dashboard
- kill switches
- audit exports
- controlled visible probability release

Exit criteria:
- internal analysts can use the platform with auditability
- rollback path tested
- visible probability only enabled for signed-off boroughs/templates

---

## 26. Immediate coding checklist

The first Codex pass should implement these files and modules in this order.

```text
services/
  api/
    app/main.py
    app/routes/listings.py
    app/routes/sites.py
    app/routes/scenarios.py
    app/routes/assessments.py
    app/routes/admin.py
  worker/
    app/main.py
    app/jobs/connectors.py
    app/jobs/site_build.py
    app/jobs/planning_enrich.py
    app/jobs/assessment.py
  scheduler/
    app/main.py
  web/
    app/
    components/
    lib/

python/
  landintel/
    domain/models.py
    domain/enums.py
    db/session.py
    connectors/base.py
    connectors/manual_url.py
    connectors/html_snapshot.py
    geospatial/geometry.py
    geospatial/title_linkage.py
    planning/extant_permission.py
    planning/pld_ingest.py
    planning/planning_register_normalize.py
    scenarios/suggest.py
    scenarios/normalize.py
    features/build.py
    scoring/logreg_model.py
    scoring/calibration.py
    scoring/explain.py
    valuation/residual.py
    valuation/quality.py
    evidence/assemble.py
    review/overrides.py
    monitoring/health.py
```

---

## 27. Non-negotiable engineering rules

1. Do not build a parcel-only scoring endpoint.
2. Do not show probability before scenario confirmation.
3. Do not trust listing text as planning truth.
4. Do not treat Brownfield Part 1 as PiP.
5. Do not treat missing Planning Data coverage as proof of no constraint.
6. Do not let PLD become the sole authority for labels.
7. Do not let a PDF parser become the hidden legal source of policy geometry.
8. Do not use portal connectors without compliance mode approval.
9. Do not overwrite raw source assets.
10. Do not publish a visible result if replay from frozen artifacts would fail.
11. Do not silently downgrade from `ABSTAIN` to an estimate when mandatory prerequisites are missing.
12. Do not allow economics to outrank planning bands.
13. Do not allow analyst override to delete the original model result.
14. Do not interpolate geometry strings directly into SQL.
15. Do not perform canonical spatial operations outside EPSG:27700.

---

## 28. Known hard problems and the v1 answer

## 28.1 Portal coverage
**Problem:** broad listing coverage is commercially and legally messy.  
**V1 answer:** launch with compliant connectors + manual URL intake + selected high-yield London sources. Add licensed portal feeds later.

## 28.2 Exact site boundaries
**Problem:** listings often do not expose precise polygons.  
**V1 answer:** geometry ladder + analyst edit workflow + multi-title linkage.

## 28.3 Borough policy complexity
**Problem:** London borough policy landscapes vary materially.  
**V1 answer:** borough baseline packs and rulepacks; speaking is borough-gated.

## 28.4 Prior approval and PD edge cases
**Problem:** extant rights can invalidate the “hidden planning upside” thesis.  
**V1 answer:** treat coverage gaps as manual-review or abstain conditions; do not assume absence.

## 28.5 Valuation precision
**Problem:** land-with-permission values are noisy and assumptions matter.  
**V1 answer:** range output, assumption governance, explicit quality labels, and market sense-checks.

---

## 29. Acceptance criteria for “v1 usable”

The system is “v1 usable” only when all of the following are true:

- analysts can ingest live listings and preserve snapshots
- analysts can confirm site geometry
- extant permission logic is working and auditable
- at least an initial set of London borough baseline packs is signed off
- scenarios can be suggested and confirmed
- evidence packs are useful without the model
- historical feature reconstruction works
- visible probability is calibrated and explainable
- valuation returns ranges, not fake precision
- every visible result links back to sources and audit history

---

## 30. Reference source register

The following external sources informed this specification and should be treated as the starting normative register for implementation.

[^nppf]: National Planning Policy Framework (GOV.UK, updated 7 February 2025): https://www.gov.uk/government/publications/national-planning-policy-framework--2  
[^planning-data-docs]: Planning Data documentation: https://www.planning.data.gov.uk/docs  
[^planning-application-incomplete]: Planning Data planning application dataset warning page: https://www.planning.data.gov.uk/dataset/planning-application  
[^brownfield-guidance]: Brownfield land registers guidance (GOV.UK): https://www.gov.uk/guidance/brownfield-land-registers  
[^determining-app]: Determining a planning application guidance (GOV.UK): https://www.gov.uk/guidance/determining-a-planning-application  
[^hmlr-inspire]: HM Land Registry INSPIRE Index Polygons guidance: https://www.gov.uk/guidance/inspire-index-polygons-spatial-data  
[^hmlr-nps]: HM Land Registry National Polygon Service: https://use-land-property-data.service.gov.uk/datasets/nps  
[^ea-flood]: Environment Agency Flood Map for Planning / Flood Zones: https://environment.data.gov.uk/dataset/04532375-a198-476e-985e-0579a0a11b47  
[^magic]: MAGIC (Defra): https://magic.defra.gov.uk/  
[^london-plan]: London Plan 2021: https://www.london.gov.uk/programmes-strategies/planning/london-plan/london-plan-2021  
[^planning-datamap]: GLA Planning DataMap: https://apps.london.gov.uk/planning/  
[^pld-overview]: Planning London Datahub overview: https://www.london.gov.uk/programmes-strategies/planning/digital-planning/planning-london-datahub  
[^pld-quality]: GLA Residential approvals dashboard PLD quality note: https://data.london.gov.uk/dataset/residential-approvals-dashboard-e5now/  
[^pld-api]: Planning London Datahub API connection document: https://www.london.gov.uk/sites/default/files/planninglondondatahub_api_connection_technical_documentation_v1.pdf  
[^ptal]: TfL Public Transport Accessibility Levels dataset: https://data.london.gov.uk/dataset/public-transport-accessibility-levels-24rz6/  
[^designated-open-space]: GLA Designated Open Space dataset: https://data.london.gov.uk/dataset/designated-open-space-e195k/  
[^listed-building]: Planning Data listed building dataset: https://www.planning.data.gov.uk/dataset/listed-building  
[^listed-building-outline]: Planning Data listed building outline dataset: https://www.planning.data.gov.uk/dataset/listed-building-outline  
[^conservation-incomplete]: Planning Data conservation area dataset: https://www.planning.data.gov.uk/dataset/conservation-area  
[^tree-preservation-incomplete]: Planning Data tree preservation zone dataset: https://www.planning.data.gov.uk/dataset/tree-preservation-zone  
[^article4-incomplete]: Planning Data article 4 direction dataset: https://www.planning.data.gov.uk/dataset/article-4-direction  
[^lpa-boundary]: Planning Data local planning authority dataset: https://www.planning.data.gov.uk/dataset/local-planning-authority  
[^price-paid]: HM Land Registry Price Paid Data: https://www.gov.uk/government/collections/price-paid-data  
[^ukhpi]: UK House Price Index reports: https://www.gov.uk/government/collections/uk-house-price-index-reports  
[^pins-casework]: Planning Inspectorate Casework Database: https://www.gov.uk/government/publications/planning-inspectorate-appeals-database  
[^supabase-postgis]: Supabase PostGIS docs: https://supabase.com/docs/guides/database/extensions/postgis  
[^supabase-storage]: Supabase Storage docs: https://supabase.com/docs/guides/storage  
[^supabase-pitr]: Supabase PITR docs: https://supabase.com/docs/guides/platform/manage-your-usage/point-in-time-recovery  
[^netlify-next]: Netlify Next.js support docs: https://docs.netlify.com/build/frameworks/framework-setup-guides/nextjs/overview/  

---
