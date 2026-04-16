# UI Refinement Hardening Plan

**Goal:** Remove current frontend clutter, fix responsive/layout breakage, standardize dense-data presentation, and leave the Next.js analyst workspace ready for PR review without changing product scope.

**Scope:** `services/web` only. Preserve existing route purposes, auth behavior, API contracts, and Phase 8A constraints.

**Assumptions**
- The current visual language is directionally correct for an internal analyst tool, so this pass should refine and normalize it rather than redesign the product.
- The biggest usability regressions are structural: mobile shell clutter, dense-table responsiveness, and detail/map surfaces with fixed-width internals.
- Browser console review is based on the running local app at `http://localhost:3000/`; current app-level findings are layout issues plus Chromium headless WebGL warnings from MapLibre, not JavaScript runtime errors.

## Workstreams

### 1. Shell and hierarchy
- Reduce duplicate chrome in the authenticated shell.
- Add a compact mobile navigation/session pattern instead of dumping the full sidebar above page content.
- Tighten spacing, panel headers, and action alignment so route content reads before chrome.

### 2. Dense-data responsiveness
- Standardize responsive table behavior for listings, clusters, sites, assessments, opportunities, and other table-driven views.
- Replace clipped/truncated mobile tables with stacked row layouts that stay scannable.
- Relax desktop fixed-width assumptions that currently squeeze warning/evidence text.

### 3. Detail-page overflow fixes
- Fix mobile horizontal overflow on site and assessment detail surfaces.
- Constrain map overlays, definition grids, and split panels to viewport width.
- Reduce oversized content blocks and normalize long-text wrapping in evidence/provenance areas.

### 4. Verification
- Re-run frontend lint, typecheck, and production build.
- Re-run an authenticated browser audit for the main routes at desktop and mobile widths.
- Confirm no app JavaScript errors remain and document any residual non-app browser warnings separately.
