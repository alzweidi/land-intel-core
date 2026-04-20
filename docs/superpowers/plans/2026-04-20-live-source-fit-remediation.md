# Phase 8A Live Source Fit Remediation

## Goal

Correct the current Phase 8A live stack so the real-data pipeline is truthful for the user's target:
- remove seeded placeholder automated-source leakage from the live scheduler path
- narrow the Cabinet Office automated source to land-like London opportunities instead of mixed operational/building-heavy rows
- ensure auto-site promotion only creates live sites from rows that match the narrowed source intent

## Scope

In scope:
- `listing_source` seed and live-source migration behavior
- Cabinet Office tabular-feed transform and refresh-policy gating
- auto-site build eligibility
- setup/runtime proof and regression coverage

Out of scope:
- broader visible-probability rollout
- portal-specific scrapers
- new later-phase source families or public SaaS behavior

## Assumptions

- The Cabinet Office feed remains an acceptable compliant automated source for internal Phase 8A use.
- The correct near-term launch posture is a narrower, more honest opportunity queue rather than a larger but misleading mixed-property queue.
- Placeholder/demo automated sources should not remain active in the live automated scheduler path.

## Planned Changes

1. Disable `example_public_page` from automated live scheduling while preserving manual-only safe sources.
2. Tighten the Cabinet Office source policy and transform to:
   - require configured authority matches rather than any `London` town/region fallback
   - accept only land-like usage/type rows suitable for Phase 8A internal land opportunity surfacing
   - exclude sold/disposed rows and retain only active market states
3. Narrow auto-site build eligibility so Cabinet Office building-heavy rows do not auto-promote into sites/opportunities.
4. Add regression tests for source filtering, scheduler/source truth, and live opportunity eligibility.
5. Rebuild the local stack and verify the resulting listings/sites/opportunities match the corrected intent.
