#!/usr/bin/env bash
# ------------------------------------------------------------------
# Land Intel — One-command local setup
#
# Runs inside the running Docker Compose stack to:
#   1. Load London borough boundaries and title polygons
#   2. Load planning, policy, brownfield, flood, heritage data
#   3. Load valuation data (HMLR prices, UKHPI, land comps)
#   4. Build and activate the hidden probability model
#
# Usage:
#   docker compose up --build -d   # start the stack first
#   bash scripts/setup_local.sh    # then run this
#
# All fixture data lives in tests/fixtures/ — nothing to download.
# ------------------------------------------------------------------

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

API_URL="${API_URL:-http://localhost:8000}"
REAL_SOURCE_KEY="${REAL_SOURCE_KEY:-cabinet_office_surplus_property}"
AUTO_SOURCE_TIMEOUT_SECONDS="${AUTO_SOURCE_TIMEOUT_SECONDS:-180}"

log()  { echo -e "${CYAN}[setup]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; exit 1; }

count_collection_items() {
    local url=$1
    python3 -c '
import json
import subprocess
import sys

payload = subprocess.check_output(["curl", "-sf", sys.argv[1]], text=True)
parsed = json.loads(payload)
if isinstance(parsed, list):
    print(len(parsed))
elif isinstance(parsed, dict):
    items = parsed.get("items")
    print(len(items) if isinstance(items, list) else 0)
else:
    print(0)
' "${url}"
}

wait_for_nonzero_count() {
    local description=$1
    local url=$2
    local timeout_seconds=$3

    log "Waiting for ${description} ..."
    for i in $(seq 1 "${timeout_seconds}"); do
        local count
        count=$(count_collection_items "${url}" || echo "0")
        if [ "${count}" -gt 0 ] 2>/dev/null; then
            ok "${description} ready (${count})"
            return 0
        fi
        sleep 1
    done
    return 1
}

# ------------------------------------------------------------------
# Wait for API to be ready
# ------------------------------------------------------------------
log "Waiting for API at ${API_URL} ..."
for i in $(seq 1 30); do
    if curl -sf "${API_URL}/readyz" > /dev/null 2>&1; then
        ok "API is ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        fail "API not reachable after 30s. Is docker compose up?"
    fi
    sleep 1
done

# ------------------------------------------------------------------
# Step 1: Borough boundaries + HMLR title polygons
# ------------------------------------------------------------------
log "Step 1/4 — Loading London borough boundaries and title polygons ..."
docker compose exec -T api python -m landintel.geospatial.bootstrap \
    --dataset all --requested-by local-setup
ok "Borough boundaries and title polygons loaded"

# ------------------------------------------------------------------
# Step 2: Planning, policy, brownfield, flood, heritage, rulepacks
# ------------------------------------------------------------------
log "Step 2/4 — Loading planning, policy, brownfield, flood, heritage, and rulepack data ..."
docker compose exec -T api python -m landintel.planning.bootstrap \
    --dataset all --requested-by local-setup
ok "Planning and policy data loaded"

# ------------------------------------------------------------------
# Step 3: Valuation data (HMLR prices, UKHPI, land comps, assumptions)
# ------------------------------------------------------------------
log "Step 3/4 — Loading valuation data (HMLR prices, UKHPI, land comps) ..."
docker compose exec -T api python -m landintel.valuation.bootstrap \
    --dataset all --requested-by local-setup
ok "Valuation data loaded"

# ------------------------------------------------------------------
# Step 4: Build and activate the hidden probability model
# ------------------------------------------------------------------
log "Step 4/4 — Building hidden probability model release ..."
RELEASE_OUTPUT=$(docker compose exec -T api python - <<'PY'
from landintel.config import get_settings
from landintel.db.session import get_session_factory
from landintel.scoring.release import build_hidden_model_releases
from landintel.storage.factory import build_storage

settings = get_settings()
session_factory = get_session_factory(settings.database_url, settings.database_echo)
storage = build_storage(settings)

with session_factory() as session:
    releases = build_hidden_model_releases(
        session=session,
        storage=storage,
        requested_by="local-setup",
        auto_activate_hidden=True,
    )
    session.commit()
    active_hidden = [release for release in releases if release.status.value == "ACTIVE"]
    if not active_hidden:
        raise SystemExit("No active hidden release was created.")
    print(", ".join(sorted(f"{release.template_key}:{release.status.value}" for release in releases)))
PY
)
ok "Hidden model release built and activated (${RELEASE_OUTPUT})"

# ------------------------------------------------------------------
# Step 5: Trigger the real automated source and wait for the pipeline
# ------------------------------------------------------------------
if curl -sf "${API_URL}/api/listings/sources" | grep -q "\"name\":\"${REAL_SOURCE_KEY}\""; then
    log "Step 5/5 — Triggering approved automated source (${REAL_SOURCE_KEY}) ..."
    curl -sf -X POST "${API_URL}/api/listings/connectors/${REAL_SOURCE_KEY}/run" \
        -H 'Content-Type: application/json' \
        -d '{"requested_by":"local-setup"}' >/dev/null
    ok "Approved automated source enqueued"

    if wait_for_nonzero_count \
        "real listing rows" \
        "${API_URL}/api/listings?source=${REAL_SOURCE_KEY}" \
        "${AUTO_SOURCE_TIMEOUT_SECONDS}"; then
        :
    else
        warn "No qualifying live listing rows were produced for ${REAL_SOURCE_KEY}; the source may not contain parcel-grade land opportunities right now."
    fi
    if wait_for_nonzero_count \
        "listing clusters" \
        "${API_URL}/api/listing-clusters" \
        "${AUTO_SOURCE_TIMEOUT_SECONDS}"; then
        :
    else
        warn "No listing clusters were produced after automated refresh; the source may have yielded zero qualifying rows."
    fi
    if wait_for_nonzero_count \
        "site candidates" \
        "${API_URL}/api/sites" \
        "${AUTO_SOURCE_TIMEOUT_SECONDS}"; then
        :
    else
        warn "No site candidates were auto-promoted for ${REAL_SOURCE_KEY}; live listings may still be too sparse or filtered."
    fi
    if wait_for_nonzero_count \
        "opportunities" \
        "${API_URL}/api/opportunities/" \
        "${AUTO_SOURCE_TIMEOUT_SECONDS}"; then
        :
    else
        warn "No opportunities were produced after the automated refresh; review the source fit and planning coverage before widening scope."
    fi
else
    warn "Approved automated source ${REAL_SOURCE_KEY} is not present in /api/listings/sources; skipping real-data trigger."
fi

# ------------------------------------------------------------------
# Done
# ------------------------------------------------------------------
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${CYAN}Web UI:${NC}        http://localhost:3000"
echo -e "  ${CYAN}API:${NC}           http://localhost:8000"
echo -e "  ${CYAN}API docs:${NC}      http://localhost:8000/docs"
echo ""
echo -e "  ${YELLOW}Next step:${NC} Open the live surfaces:"
echo -e "  ${CYAN}http://localhost:3000/listings${NC}"
echo -e "  ${CYAN}http://localhost:3000/listing-clusters${NC}"
echo -e "  ${CYAN}http://localhost:3000/sites${NC}"
echo -e "  ${CYAN}http://localhost:3000/opportunities${NC}"
echo ""
