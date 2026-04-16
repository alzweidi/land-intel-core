# Land Intel — Usage Guide

How to set up the platform locally, feed it land listing URLs, and see it score planning
permission probability and rank opportunities in the web UI.

---

## What This System Actually Does

Land Intel is an **analysis engine**, not a web scraper. It does not automatically go
find land for sale. The workflow is:

1. **You give it listing URLs** (e.g. Rightmove, auction sites) or upload a CSV of listings
2. It **fetches, parses, and deduplicates** the listings
3. You **promote a listing to a "site"** — the system then enriches it with planning data,
   borough boundaries, flood zones, heritage, brownfield status, etc.
4. You **generate scenarios** (e.g. "build 1-4 homes here with full planning")
5. The **probability engine scores** how likely planning permission is to be granted
6. The **valuation engine** estimates post-permission value and uplift
7. All results appear in the **web UI** as a ranked opportunity list

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

**You don't need to find or download any data.** It's all fixture files already in the repo.

When the script finishes, you'll see "Setup complete!" and you're ready to analyze listings.

---

## Step 3: Feed It A Listing

Go find a land listing on Rightmove, an auction site, or any property portal. Copy the URL.

### Option A: Use the Web UI (easiest)

1. Open http://localhost:3000
2. Click **"Run connector"** (or go to http://localhost:3000/admin/source-runs)
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

**Web UI:** http://localhost:3000/scenarios or from the site detail page.

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
> setup script, run this first:
> ```bash
> curl -X POST http://localhost:8000/api/admin/model-releases/rebuild \
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

### 8.1 View the assessment

**Standard view (redacted — no probability shown):**

```bash
curl http://localhost:8000/api/assessments/<assessment_uuid> | python -m json.tool
```

**Hidden mode (shows the probability estimate, model metadata, comparables, valuation):**

```bash
curl 'http://localhost:8000/api/assessments/<assessment_uuid>?hidden_mode=true' | python -m json.tool
```

**Web UI:** http://localhost:3000/assessments — click into an assessment. Add `?mode=hidden` to the URL for the full internal view with:
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

Each opportunity shows:
- **Probability band** (A = most likely to get permission, Hold = not enough data)
- **Post-permission value** and **expected uplift** (from the valuation engine)
- **Asking price** (from the listing)
- **Manual review** flags
- **Ranking reason** (why it's in that position)

Filter by borough, band, valuation quality, price range, or auction deadline.

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
curl -X POST http://localhost:8000/api/admin/model-releases/rebuild \
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

| URL | What it shows |
|---|---|
| `/` | Control room dashboard |
| `/listings` | All parsed listings with search |
| `/listing-clusters` | Deduplicated listing groups |
| `/admin/source-runs` | Connector control — trigger manual URL, CSV, or approved sources |
| `/sites` | Site candidates on a MapLibre map with filters |
| `/sites/<id>` | Site detail — geometry, planning context, evidence, scenarios |
| `/scenarios` | Scenario browser |
| `/assessments` | Frozen assessment list (add `?mode=hidden` for scoring) |
| `/assessments/<id>` | Assessment detail with evidence, comparables, valuation |
| `/opportunities` | Planning-first ranked opportunity table |
| `/review-queue` | Gold-set review and exception cases |
| `/data-health` | Source freshness and coverage dashboard |
| `/admin/health` | System health — jobs, services |
| `/admin/model-releases` | Hidden model release registry |

---

## Troubleshooting

| Problem | Fix |
|---|---|
| **"No listings found"** | Check the worker is running. Check `/api/admin/jobs` for failed jobs. |
| **Site has no planning context** | Run the planning bootstrap first (`python -m landintel.planning.bootstrap --dataset all`). |
| **Assessment shows "NONE" estimate** | Rebuild model releases and make sure at least one is activated. |
| **Opportunities all show "Hold"** | Either no model release is active, or the scenario template doesn't have enough historical support. Check `/admin/model-releases`. |
| **Map is blank** | The default map style is `https://demotiles.maplibre.org/style.json` — it needs internet access. |
| **Database connection refused** | Make sure Postgres is running: `docker compose up postgres -d` and check the `DATABASE_URL` env var. |

---

## What's Next: Going To Production

See [DEPLOY.md](/DEPLOY.md) for the full production deployment guide covering:
- Supabase setup (Postgres, Storage, Auth)
- VPS deployment with Docker + Caddy
- Netlify frontend deployment
- DNS, TLS, and site protection
- Rollback and backup procedures
