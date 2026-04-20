# Land Intel — Usage Guide

How to set up the platform locally, trigger the real automated source, optionally feed it land listing URLs, and see it score planning
permission probability and rank opportunities in the web UI.

---

## What This System Actually Does

Land Intel is an **analysis engine** with a narrow approved automation path. It does not
ship arbitrary portal scrapers. The workflow is:

1. It can **pull approved automated sources** such as the Cabinet Office surplus-property register
2. You can also **give it listing URLs** or upload a CSV of listings when analyst-triggered intake is still needed
3. It **fetches, parses, and deduplicates** the listings
4. It auto-promotes eligible live land clusters into sites, then enriches them with planning data,
   borough boundaries, flood zones, heritage, brownfield status, etc.
5. You review or confirm scenarios when needed
6. The **probability engine scores** how likely planning permission is to be granted
7. The **valuation engine** estimates post-permission value and uplift
8. All results appear in the **web UI** as a ranked opportunity list

All the planning/policy/valuation reference data is **already included in this repo** as
fixture files under `tests/fixtures/`. You don't need to download anything.

---

## Prerequisites

You only need **Docker** installed. That's it.

```bash
docker --version          # any recent version
docker compose version    # needs the compose plugin
```

---

## Step 1: Start Everything

```bash
cp .env.example .env
docker compose up --build
```

Wait until you see output like the screenshot — all services green. You now have:

- **Web UI** → http://localhost:3000
- **API** → http://localhost:8000

**Leave this terminal running.**

## Step 1.5: Sign In To The Web UI

The current Phase 8A web app uses built-in local role accounts with a signed cookie session.

| Role | Email | Password |
|---|---|---|
| Analyst | `analyst@landintel.local` | `analyst-demo` |
| Reviewer | `reviewer@landintel.local` | `reviewer-demo` |
| Admin | `admin@landintel.local` | `admin-demo` |

Open `http://localhost:3000/login`, choose the role you want to test, and then continue with the setup flow below.

Route access is role-aware:

- analyst: `/`, `/listings`, `/listing-clusters`, `/sites`, `/scenarios`, `/assessments`, `/opportunities`
- reviewer: analyst routes plus `/review-queue`
- admin: reviewer routes plus `/admin/source-runs`, `/admin/health`, and `/admin/model-releases`

Reviewer/admin and hidden-mode access is granted from the signed web session only. Query/body
fields such as `viewer_role`, `actor_role`, or `hidden_mode` are not trusted as authority.

## Step 2: Run The Setup Script (one command, does everything)

Open a **new terminal** and run:

```bash
bash scripts/setup_local.sh
```

This single script automatically:

1. Loads London borough boundaries and HMLR title polygons (from `tests/fixtures/reference/`)
2. Loads planning history, policy areas, brownfield, flood, heritage data (from `tests/fixtures/planning/`)
3. Loads HMLR house prices, UKHPI index, and land comp data (from `tests/fixtures/valuation/`)
4. Builds and activates the hidden probability model (trains a logistic regression on the historical planning data)
5. Triggers the approved automated source `cabinet_office_surplus_property`
6. Waits for live listings, clusters, sites, and opportunities to appear before returning success

**You don't need to find or download any data.** It's all fixture files already in the repo.
The real automated source is pulled live; the planning and valuation baseline remains fixture-backed unless you configure additional official source URLs in `.env`.

When the script finishes, you'll see "Setup complete!" and you're ready to analyze listings.
If the API is not reachable or no active hidden release is created, the script exits non-zero
instead of claiming success.

---

## Step 3: Feed It Additional Listings (optional)

The setup script already triggers the approved automated source and waits for real rows to appear.
Use this step when you also want to add analyst-triggered URLs or CSV imports.

### Option A: Use the Web UI (easiest)

This route is **admin-only** in the current web app.

1. Sign in as `admin@landintel.local`
2. Open http://localhost:3000/admin/source-runs
3. Paste your listing URL into the **Manual URL** form and submit

### Option B: Use curl

```bash
curl -X POST http://localhost:8000/api/listings/intake/url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.rightmove.co.uk/properties/123456789","source_name":"manual_url"}'
```

### Option C: Upload a CSV of multiple listings

```bash
curl -X POST http://localhost:8000/api/listings/import/csv \
  -F source_name=csv_import \
  -F file=@/path/to/your/listings.csv
```

CSV columns: `url`, `address`, `price`, `lat`, `lon`, `headline`, `description`.

### What happens next

The **worker** (running in Docker) automatically picks up the job, fetches the page, parses it,
and stores an immutable snapshot. This takes a few seconds.

**Check the result:**

- Open http://localhost:3000/listings — your listing should appear
- Open http://localhost:3000/listing-clusters — it will be grouped into a deduplicated cluster

---

## Step 4: Promote A Listing To A Site

A **site** is the unit of analysis. You promote a listing cluster to a site candidate.
The system then automatically enriches it with planning data, borough/LPA assignment,
title polygons, flood zones, heritage, etc.

### 4.1 Pick a cluster

```bash
# List clusters and grab a cluster_id
curl http://localhost:8000/api/listing-clusters | python -m json.tool
```

### 4.2 Create a site from it

```bash
curl -X POST http://localhost:8000/api/sites/from-cluster/<cluster_uuid> \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'
```

This:
- Creates a `site_candidate` with draft geometry (from listing coordinates)
- Assigns the London borough / LPA
- Links any overlapping HMLR title polygons
- Triggers the planning enrichment pipeline (permissions, policy, brownfield, flood, heritage, Article 4)

### 4.3 Check it in the UI

Go to **http://localhost:3000/sites** — you'll see the site on a MapLibre map with:
- Borough and LPA assignment
- Geometry confidence level
- Listing headline and price
- Any warning flags

Click into a site for the full detail view with planning context, evidence, and source coverage.

### 4.4 (Optional) Edit the geometry

If the auto-generated geometry is rough, draw a better one:

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/geometry \
  -H 'Content-Type: application/json' \
  -d '{
    "geom_4326": {
      "type": "Polygon",
      "coordinates": [[[-0.12,51.52],[-0.119,51.52],[-0.119,51.521],[-0.12,51.521],[-0.12,51.52]]]
    },
    "source_type": "ANALYST_DRAWN",
    "confidence": "HIGH",
    "reason": "Corrected from OS map",
    "created_by": "local-smoke"
  }'
```

Or use the geometry editor in the site detail view.

---

## Step 5: Run The Planning Permission Check

Check whether a site already has planning permission (which would exclude it from the opportunity pipeline):

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/extant-permission-check \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'
```

Results appear in the site detail view under "Extant permission" — showing `FOR`/`AGAINST`/`UNKNOWN` evidence.

---

## Step 6: Generate And Confirm Scenarios

A **scenario** is a development hypothesis (e.g. "build 1-4 residential units with full planning"). The probability engine scores these.

### 6.1 Suggest scenarios for a site

```bash
curl -X POST http://localhost:8000/api/sites/<site_uuid>/scenarios/suggest \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'
```

This creates deterministic scenario suggestions based on the site's planning context and the v1 templates (`resi_1_4_full`, `resi_5_9_full`, `resi_10_49_outline`).

### 6.2 View scenarios

**Web UI:** site-specific scenarios are reviewed from the site detail page or `http://localhost:3000/sites/<site_uuid>/scenario-editor`.

The top-level `http://localhost:3000/scenarios` route is a template index only. It does not show the live scenario list for a site.

```bash
curl http://localhost:8000/api/sites/<site_uuid>/scenarios | python -m json.tool
```

### 6.3 Confirm a scenario (required before scoring)

```bash
curl -X POST http://localhost:8000/api/scenarios/<scenario_uuid>/confirm \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "confirm",
    "reviewed_by": "local-smoke",
    "review_notes": "Looks reasonable for this site context."
  }'
```

---

## Step 7: Create An Assessment (Run The Probability Engine)

> The setup script already built the probability model in Step 2. If you skipped the
> setup script, log in as admin through the web proxy and run this first:
> ```bash
> curl -c /tmp/landintel-admin.cookies \
>   -X POST http://localhost:3000/api/auth/login \
>   -H 'Content-Type: application/x-www-form-urlencoded' \
>   --data-urlencode 'email=admin@landintel.local' \
>   --data-urlencode 'password=admin-demo' \
>   --data-urlencode 'next=/admin/model-releases'
> curl -b /tmp/landintel-admin.cookies \
>   -X POST http://localhost:3000/api/admin/model-releases/rebuild \
>   -H 'Content-Type: application/json' \
>   -d '{"requested_by":"local-dev","auto_activate_hidden":true}'
> ```

This is the key step — it freezes point-in-time features, runs the hidden scoring model, and produces a probability estimate:

```bash
curl -X POST http://localhost:8000/api/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "site_id": "<site_uuid>",
    "scenario_id": "<confirmed_scenario_uuid>",
    "as_of_date": "2026-04-16",
    "requested_by": "local-smoke"
  }'
```

### 7.1 View the assessment

**Standard view (redacted — no probability shown):**

```bash
curl http://localhost:8000/api/assessments/<assessment_uuid> | python -m json.tool
```

**Hidden mode (requires a reviewer/admin web session and shows the probability estimate, model metadata, comparables, valuation):**

```bash
curl -c /tmp/landintel-reviewer.cookies \
  -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=reviewer@landintel.local' \
  --data-urlencode 'password=reviewer-demo' \
  --data-urlencode 'next=/assessments'

curl -b /tmp/landintel-reviewer.cookies \
  'http://localhost:3000/api/assessments/<assessment_uuid>?hidden_mode=true' | python -m json.tool
```

**Web UI:** http://localhost:3000/assessments — click into an assessment. Reviewer/admin sessions can add `?mode=hidden` to the detail URL for the full internal view with:
- Hidden probability band (A/B/C/D)
- Estimate quality and OOD status
- Explanation drivers
- Comparable cases
- Valuation block (post-permission value, uplift, sense-check)

---

## Step 8: See The Ranked Opportunities

The opportunity ranking combines planning probability, valuation, and urgency into a planning-first ranked list:

**Web UI:** http://localhost:3000/opportunities

**API:**

```bash
curl http://localhost:8000/api/opportunities | python -m json.tool
```

Reviewer/admin users can open `http://localhost:3000/opportunities?includeHidden=true` to request the hidden/internal queue view. The standard queue still shows planning bands, but hidden-only fields such as expected uplift remain redacted there.

Each opportunity shows:
- **Probability band** (A = most likely to get permission, Hold = not enough data)
- **Post-permission value** and valuation quality
- **Asking price** (from the listing)
- **Manual review** flags
- **Ranking reason** (why it's in that position)

The current web UI filters by borough, band, valuation quality, manual-review state, and hidden/internal mode. The API additionally supports `auction_deadline_days`, `min_price`, and `max_price` even though those controls are not exposed in the current web UI.

---

## Quick Reference: The Full Pipeline In 10 Commands

```bash
# 1. Start everything
docker compose up --build -d

# 2. Bootstrap reference data (run once)
docker compose exec api python -m landintel.geospatial.bootstrap --dataset all --requested-by local-dev
docker compose exec api python -m landintel.planning.bootstrap --dataset all --requested-by local-dev
docker compose exec api python -m landintel.valuation.bootstrap --dataset all --requested-by local-dev

# 3. Ingest a listing
curl -X POST http://localhost:8000/api/listings/intake/url \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/land-for-sale","source_name":"manual_url"}'

# 4. Wait ~10s for the worker to process, then check listings
curl http://localhost:8000/api/listing-clusters

# 5. Create a site from a cluster
curl -X POST http://localhost:8000/api/sites/from-cluster/<cluster_uuid> \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'

# 6. Suggest scenarios
curl -X POST http://localhost:8000/api/sites/<site_uuid>/scenarios/suggest \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-smoke"}'

# 7. Confirm a scenario
curl -X POST http://localhost:8000/api/scenarios/<scenario_uuid>/confirm \
  -H 'Content-Type: application/json' \
  -d '{"action":"confirm","reviewed_by":"local-smoke","review_notes":"OK"}'

# 8. Build the model (run once)
curl -c /tmp/landintel-admin.cookies \
  -X POST http://localhost:3000/api/auth/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'email=admin@landintel.local' \
  --data-urlencode 'password=admin-demo' \
  --data-urlencode 'next=/admin/model-releases'
curl -b /tmp/landintel-admin.cookies \
  -X POST http://localhost:3000/api/admin/model-releases/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"requested_by":"local-dev","auto_activate_hidden":true}'

# 9. Create an assessment (runs the probability engine)
curl -X POST http://localhost:8000/api/assessments \
  -H 'Content-Type: application/json' \
  -d '{"site_id":"<site_uuid>","scenario_id":"<scenario_uuid>","as_of_date":"2026-04-16","requested_by":"local-smoke"}'

# 10. See ranked opportunities
curl http://localhost:8000/api/opportunities
```

Then open http://localhost:3000 and explore.

---

## Web UI Page Map

| URL | Access | Current state |
|---|---|---|
| `/` | analyst+ | dashboard / route launcher |
| `/listings` | analyst+ | parsed listings with filters and immutable snapshot context |
| `/listing-clusters` | analyst+ | deterministic dedupe review |
| `/admin/source-runs` | admin | connector console for manual URL, CSV, and approved sources |
| `/sites` | analyst+ | site registry with map, filters, and warning states |
| `/sites/<id>` | analyst+ | site detail with geometry, planning context, evidence, raw links, and current scenarios |
| `/sites/<id>/scenario-editor` | analyst+ | live scenario generation, compare, edit, and confirm flow |
| `/scenarios` | analyst+ | template index only; not the site-specific scenario browser |
| `/assessments` | analyst+ | frozen assessment list |
| `/assessments/<id>` | analyst+ | redacted assessment detail by default; reviewer/admin can add `?mode=hidden` |
| `/opportunities` | analyst+ | planning-first ranked queue; reviewer/admin can add `?includeHidden=true` |
| `/review-queue` | reviewer/admin | manual-review cases, blocked cases, and gold-set workflow |
| `/admin/health` | admin | primary operational health dashboard |
| `/admin/model-releases` | admin | release registry, visibility controls, and incidents |
| `/discovery` | analyst+ | non-nav placeholder shell |
| `/data-health` | analyst+ | non-nav placeholder shell |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **"No listings found"** | Check the worker is running. Check `/api/admin/jobs` for failed jobs with an authenticated admin session through `http://localhost:3000/api/...`. |
| **I cannot open `/admin/source-runs`** | That route is admin-only. Sign in with the admin demo account or use the API intake endpoints directly. |
| **Site has no planning context** | Run the planning bootstrap first (`python -m landintel.planning.bootstrap --dataset all`). |
| **`/scenarios` does not show the scenarios I just generated** | Use the site detail page or `/sites/<site_uuid>/scenario-editor`. The top-level `/scenarios` page is only the template index. |
| **Assessment shows "NONE" estimate** | Rebuild model releases and make sure at least one is activated. |
| **Hidden mode still looks redacted in the web UI** | Hidden assessment detail requires a reviewer/admin session and `?mode=hidden`. Hidden opportunity detail requires reviewer/admin plus `?includeHidden=true`. |
| **Opportunities all show "Hold"** | Either no model release is active, or the scenario template doesn't have enough historical support. Check `/admin/model-releases`. |
| **Map is blank** | The default map style is `https://demotiles.maplibre.org/style.json` — it needs internet access. |
| **Database connection refused** | Make sure Postgres is running: `docker compose up postgres -d` and check the `DATABASE_URL` env var. |

---

## What's Next: Going To Production

See [../operations/deployment.md](../operations/deployment.md) for the full production deployment guide covering:
- Supabase setup (Postgres, Storage, Auth)
- VPS deployment with Docker + Caddy
- Netlify frontend deployment
- DNS, TLS, and site protection
- Rollback and backup procedures
