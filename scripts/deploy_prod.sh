#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_prod.sh <ssh_target> <remote_dir>

Examples:
  scripts/deploy_prod.sh deploy@api.example.com /srv/land-intel-core
  scripts/deploy_prod.sh root@203.0.113.10 /opt/land-intel-core
EOF
}

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 1
fi

SSH_TARGET=$1
REMOTE_DIR=$2
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
COMPOSE_FILE="infra/compose/docker-compose.vps.yml"

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required on the local machine." >&2
  exit 1
fi

ssh "${SSH_TARGET}" "mkdir -p '${REMOTE_DIR}'"

rsync \
  --archive \
  --compress \
  --delete \
  --delete-excluded \
  --human-readable \
  --exclude '.git/' \
  --exclude '.github/' \
  --exclude '.venv/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '__pycache__/' \
  --exclude 'node_modules/' \
  --exclude 'services/web/.next/' \
  --exclude '.env' \
  --exclude '.env.production' \
  --exclude '.env.local' \
  --exclude 'services/web/.env.local' \
  "${REPO_ROOT}/" "${SSH_TARGET}:${REMOTE_DIR}/"

ssh "${SSH_TARGET}" "REMOTE_DIR='${REMOTE_DIR}' COMPOSE_FILE='${COMPOSE_FILE}' bash -se" <<'EOF'
set -euo pipefail

cd "${REMOTE_DIR}"

if [[ ! -f .env.production ]]; then
  echo "Missing ${REMOTE_DIR}/.env.production. Create it from .env.production.example first." >&2
  exit 1
fi

docker compose -f "${COMPOSE_FILE}" config >/dev/null
docker compose -f "${COMPOSE_FILE}" build
docker compose -f "${COMPOSE_FILE}" run --rm api alembic upgrade head
docker compose -f "${COMPOSE_FILE}" up -d
docker compose -f "${COMPOSE_FILE}" ps

cat <<'POST_DEPLOY'

Deployment finished.

Follow-up checks on the VPS:
  docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 api
  docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 worker
  docker compose -f infra/compose/docker-compose.vps.yml logs --tail=100 scheduler

Follow-up checks from your workstation:
  BACKEND_BASIC_AUTH_USER='<user>' BACKEND_BASIC_AUTH_PASSWORD='<password>' \
    ./scripts/smoke_prod.sh https://app.example.com https://api.example.com
POST_DEPLOY
EOF
