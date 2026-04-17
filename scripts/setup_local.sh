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

log()  { echo -e "${CYAN}[setup]${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; exit 1; }

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
echo -e "  ${YELLOW}Next step:${NC} Feed it a listing URL to analyze:"
echo ""
echo -e "  curl -X POST http://localhost:8000/api/listings/intake/url \\"
echo -e "    -H 'Content-Type: application/json' \\"
echo -e "    -d '{\"url\":\"https://www.rightmove.co.uk/properties/123456789\",\"source_name\":\"manual_url\"}'"
echo ""
echo -e "  Then open ${CYAN}http://localhost:3000/listings${NC} to see it."
echo ""
