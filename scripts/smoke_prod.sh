#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/smoke_prod.sh <app_origin> <api_origin>

Required environment variables:
  BACKEND_BASIC_AUTH_USER
  BACKEND_BASIC_AUTH_PASSWORD
EOF
}

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 1
fi

APP_ORIGIN=${1%/}
API_ORIGIN=${2%/}
: "${BACKEND_BASIC_AUTH_USER:?BACKEND_BASIC_AUTH_USER is required}"
: "${BACKEND_BASIC_AUTH_PASSWORD:?BACKEND_BASIC_AUTH_PASSWORD is required}"

auth=(
  --user
  "${BACKEND_BASIC_AUTH_USER}:${BACKEND_BASIC_AUTH_PASSWORD}"
)

check_json() {
  local description=$1
  local url=$2
  shift 2

  echo "Checking ${description}: ${url}"
  curl --fail --silent --show-error "$@" "${url}" >/dev/null
}

echo "== Backend health =="
check_json "healthz" "${API_ORIGIN}/healthz"
check_json "readyz" "${API_ORIGIN}/readyz"

echo "== Protected backend surfaces =="
check_json "data health" "${API_ORIGIN}/api/health/data" "${auth[@]}"
check_json "model health" "${API_ORIGIN}/api/health/model" "${auth[@]}"
check_json "review queue" "${API_ORIGIN}/api/admin/review-queue" "${auth[@]}"

echo "== Frontend reachability =="
app_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${APP_ORIGIN}")
case "${app_status}" in
  200|401|403)
    echo "Frontend reachable with status ${app_status}"
    ;;
  *)
    echo "Unexpected frontend status: ${app_status}" >&2
    exit 1
    ;;
esac

head_status=$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' --head "${APP_ORIGIN}")
case "${head_status}" in
  200|401|403)
    echo "Frontend HEAD reachable with status ${head_status}"
    ;;
  *)
    echo "Unexpected frontend HEAD status: ${head_status}" >&2
    exit 1
    ;;
esac

echo "Production smoke checks passed."
