# Acquisition Target Handoff

## Current Truth

- The live Phase 8A stack is working correctly after the live-source-fit remediation.
- The previous false-positive Battersea/Wandsworth site was removed by tightening source-fit and auto-site-build eligibility.
- The system now prefers truthful empty live states over inventing parcel candidates from weak evidence.
- The current approved automated source, `cabinet_office_surplus_property`, does not currently yield parcel-grade London land-for-sale opportunities.

## Verified Runtime State

- `docker compose up --build -d` succeeds.
- `docker compose exec -T api alembic upgrade head` succeeds.
- `bash scripts/setup_local.sh` succeeds.
- `bash scripts/smoke_prod.sh http://localhost:3000 http://localhost:8000` succeeds with authenticated checks.
- `ruff check .` passes.
- `pytest` passes with `401 passed` and `100.00%` coverage.
- `services/web` lint, typecheck, coverage, and build all pass.

## What Changed In This Slice

1. `example_public_page` is deactivated from the live automated path.
2. The Cabinet Office source policy is now stricter:
   - London authority matching must come from `Local Authority`
   - allowed listing types are narrowed to `LAND`
   - `max_surplus_floor_area_sqm = 0`
   - `require_positive_land_area = true`
3. Cabinet Office rows no longer auto-promote into sites unless they include explicit geometry or a valid bbox in the source payload.
4. The setup and smoke scripts now accept truthful zero-row live states instead of requiring fake positive counts.

## Hard Evidence From The Upstream Feed

As checked on April 20, 2026 against `https://data.insite.cabinetoffice.gov.uk/insite/Register.xlsx`:

- total rows: `445`
- `On the Market`: `45`
- London `On the Market`: `5`
- London `On the Market` rows with allowed land-usage patterns: `1`
- London rows that also satisfy `positive land area + zero surplus floor area`: `0`

The five London `On the Market` rows currently visible upstream are mixed operational/building inventory:

- `213-221 BOROUGH HIGH STREET, LONDON, SE1 1JA` (`Operational`)
- `714 FOREST ROAD, LONDON, E17 3HP` (`Residential`)
- `POND STREET, LONDON, NW3 2PN` (`Operational`)
- `108 LANDOR ROAD, LONDON, SW9 9NU` (`Operational`)
- `311 BATTERSEA PARK ROAD, LONDON, SW11 4LU` (`Surplus Land`, but `404.00` surplus floor area)

Conclusion: the Cabinet Office feed currently does not contain the user's actual acquisition target.

## What Tomorrow Needs To Achieve

The next slice is not about fixing the current code path again. It is about finding and onboarding a source that actually contains:

- land for sale
- parcel-grade or near-parcel-grade opportunity records
- no existing planning permission proven by the source itself
- enough geometry/location evidence to create a truthful site candidate

## Required Next Steps

1. Source strategy
   - Identify one or more compliant automated sources that actually publish parcel-grade land-for-sale opportunities.
   - Do not add portal-specific scrapers without explicit compliance approval.
   - If no compliant automated source exists, define an approved analyst-triggered intake stopgap rather than pretending the automated target is solved.

2. Acquisition-target contract
   - Write down the exact inclusion rule for the desired target:
     - active market listing
     - land parcel or redevelopment land lot
     - no standing planning permission proven by authority-grade data
     - sufficient geometry evidence for a bounded site candidate
   - Separate "planning unknown" from "no planning permission" so the system stays honest.

3. Source-fit policy for the next real source
   - Require explicit parcel geometry, site plan geometry, or a trustworthy bbox / polygon source.
   - Do not auto-promote title-union-only evidence into sites.
   - Add source-specific row filters for lot/land-only inventory.

4. Planning evidence completeness
   - Expand borough planning-register / brownfield / prior-approval / local constraint coverage for the boroughs targeted by the new source.
   - Without this, opportunities will correctly stay in `Hold` / abstain states.

5. First-source launch gate
   - Run the new automated source in isolation.
   - Confirm it creates `source_snapshot`, `raw_asset`, listing rows, clusters, and only truthful site candidates.
   - Sample-check at least five rows manually before leaving the source active in scheduler cadence.

## Definition Of Success For The Next Slice

Tomorrow's work is successful only if the live frontend shows real parcel-grade land opportunities that survive source-fit checks without needing title-union inflation or fixture fallback. If the next candidate source still bottoms out at zero truthful rows, keep the UI empty and continue source onboarding rather than weakening the rules.
