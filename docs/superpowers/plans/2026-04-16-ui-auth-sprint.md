# UI/Auth Sprint Implementation Plan

**Goal:** Turn the current scaffolded analyst shell into a coherent internal product UI with real local/dev auth, role-aware route protection, and usable dense analyst surfaces on top of the existing live API.

**Scope:** Frontend and auth only. Keep backend business logic, scoring logic, and API contracts intact unless a small UI-enabling fix is unavoidable.

**Assumptions**
- Local/dev remains the priority; no production deployment work is included.
- Supabase Auth is the intended long-term auth path, but local/dev needs a working role-aware session flow now.
- Existing API query parameters for `viewer_role`, `hidden_mode`, and `actor_role` remain the bridge from frontend session state to backend behavior.
- Visible probability stays hidden by default.

## Workstreams

### 1. Auth and session
- Add a real login flow for local/dev that uses a maintainable auth adapter boundary.
- Protect application routes and redirect anonymous users to login.
- Resolve one current user and role per request, then map that role into existing API calls.
- Enforce role-aware UI states:
  - `analyst`: standard product surfaces, redacted hidden/internal details
  - `reviewer`: hidden/internal assessment and queue surfaces
  - `admin`: release and control-plane actions

### 2. Product shell and shared primitives
- Replace scaffold copy and placeholder chrome in the app shell.
- Introduce a denser internal layout system with:
  - authenticated header
  - product-aligned side navigation
  - compact summary cards
  - status chip system
  - table/list primitives
  - evidence and provenance primitives
  - section/tab or split-panel patterns where needed

### 3. Page redesign
- Redesign the existing routes without changing their purpose:
  - listings
  - listing cluster detail
  - sites list/detail
  - scenario editor
  - assessments list/detail
  - opportunities
  - review queue
  - admin health
  - model releases
- Ensure laptop-width layouts do not overflow or leak text.
- Make maps large enough to support actual analyst review.
- Make assessment and opportunity pages feel like working analyst tools, not landing pages.

### 4. Verification
- Run frontend lint, typecheck, and production build.
- Run targeted backend/frontend tests only where UI-enabling wiring changed.
- Rerun the local demo walkthrough on the live stack.
- Capture fresh screenshots for the major product surfaces.

## Planned File Ownership

### Auth/session slice
- `services/web/app/login/page.tsx`
- `services/web/app/(protected or equivalent routing changes)`
- `services/web/lib/auth/*`
- `services/web/middleware.ts`
- any minimal auth UI components

### Shared shell/design slice
- `services/web/app/layout.tsx`
- `services/web/app/globals.css`
- `services/web/components/app-shell.tsx`
- `services/web/components/sidebar-nav.tsx`
- `services/web/components/ui.tsx`
- new shared UI primitives under `services/web/components/`
- `services/web/lib/navigation.ts`

### Page wiring slice
- `services/web/app/listings/*`
- `services/web/app/listing-clusters/*`
- `services/web/app/sites/*`
- `services/web/app/assessments/*`
- `services/web/app/opportunities/*`
- `services/web/app/review-queue/*`
- `services/web/app/admin/*`
- `services/web/lib/landintel-api.ts` only as needed for session-aware role wiring or live-data bug fixes

