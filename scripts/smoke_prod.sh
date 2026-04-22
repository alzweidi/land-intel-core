#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/smoke_prod.sh <app_origin> <api_origin>

Required environment variables:
  BACKEND_BASIC_AUTH_USER
  BACKEND_BASIC_AUTH_PASSWORD

Optional environment variables:
  APP_CURL_CONFIG
  APP_OUTER_BASIC_AUTH_USER
  APP_OUTER_BASIC_AUTH_PASSWORD
  APP_AUTH_EMAIL
  APP_AUTH_PASSWORD

Local localhost fallback:
  If APP_AUTH_EMAIL / APP_AUTH_PASSWORD are unset and APP_ORIGIN is localhost,
  the script uses the built-in local admin account.

APP_CURL_CONFIG:
  Optional curl config file applied to every APP_ORIGIN request. Use this for
  Netlify site protection or any outer frontend access layer that needs a
  cookie, header, client certificate, or other curl options before app login.
EOF
}

if [[ $# -ne 2 ]]; then
  usage >&2
  exit 1
fi

APP_ORIGIN=${1%/}
API_ORIGIN=${2%/}
REAL_SOURCE_KEY=${REAL_SOURCE_KEY:-bidwells_land_development}
: "${BACKEND_BASIC_AUTH_USER:?BACKEND_BASIC_AUTH_USER is required}"
: "${BACKEND_BASIC_AUTH_PASSWORD:?BACKEND_BASIC_AUTH_PASSWORD is required}"

auth=(
  --user
  "${BACKEND_BASIC_AUTH_USER}:${BACKEND_BASIC_AUTH_PASSWORD}"
)

app_origin_curl=()
if [[ -n "${APP_CURL_CONFIG:-}" ]]; then
  if [[ ! -f "${APP_CURL_CONFIG}" ]]; then
    echo "APP_CURL_CONFIG does not exist: ${APP_CURL_CONFIG}" >&2
    exit 1
  fi
  app_origin_curl+=(
    --config
    "${APP_CURL_CONFIG}"
  )
fi

if [[ -n "${APP_OUTER_BASIC_AUTH_USER:-}" || -n "${APP_OUTER_BASIC_AUTH_PASSWORD:-}" ]]; then
  if [[ -z "${APP_OUTER_BASIC_AUTH_USER:-}" || -z "${APP_OUTER_BASIC_AUTH_PASSWORD:-}" ]]; then
    echo "APP_OUTER_BASIC_AUTH_USER and APP_OUTER_BASIC_AUTH_PASSWORD must be set together." >&2
    exit 1
  fi
  app_origin_curl+=(
    --user
    "${APP_OUTER_BASIC_AUTH_USER}:${APP_OUTER_BASIC_AUTH_PASSWORD}"
  )
fi

cookie_jar=$(mktemp)
login_headers=$(mktemp)
cleanup() {
  rm -f "${cookie_jar}" "${login_headers}"
}
trap cleanup EXIT

resolve_app_auth_email() {
  if [[ -n "${APP_AUTH_EMAIL:-}" ]]; then
    printf '%s' "${APP_AUTH_EMAIL}"
    return 0
  fi

  case "${APP_ORIGIN}" in
    http://localhost*|http://127.0.0.1*|https://localhost*|https://127.0.0.1*)
      printf '%s' 'admin@landintel.local'
      return 0
      ;;
  esac

  return 1
}

resolve_app_auth_password() {
  if [[ -n "${APP_AUTH_PASSWORD:-}" ]]; then
    printf '%s' "${APP_AUTH_PASSWORD}"
    return 0
  fi

  case "${APP_ORIGIN}" in
    http://localhost*|http://127.0.0.1*|https://localhost*|https://127.0.0.1*)
      printf '%s' 'admin-demo'
      return 0
      ;;
  esac

  return 1
}

check_json() {
  local description=$1
  local url=$2
  shift 2

  echo "Checking ${description}: ${url}"
  curl_cmd --fail --silent --show-error "$@" "${url}" >/dev/null
}

curl_cmd() {
  local url="${!#}"
  local command=("${CURL_BIN:-curl}")
  if [[ "${url}" == "${APP_ORIGIN}"* ]] && (( ${#app_origin_curl[@]} )); then
    command+=("${app_origin_curl[@]}")
  fi
  command+=("$@")
  "${command[@]}"
}

count_collection_items() {
  local url=$1
  shift

  local payload
  payload=$(curl_cmd --fail --silent --show-error "$@" "${url}")

  python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if isinstance(payload, list):
    print(len(payload))
elif isinstance(payload, dict):
    items = payload.get("items")
    if isinstance(items, list):
        print(len(items))
    else:
        print(0)
else:
    print(0)
' <<<"${payload}"
}

check_count_positive() {
  local description=$1
  local url=$2
  shift 2

  echo "Checking ${description} count: ${url}"
  local count
  count=$(count_collection_items "${url}" "$@")
  if [[ "${count}" -lt 1 ]]; then
    echo "Expected at least one row for ${description}, found ${count}" >&2
    exit 1
  fi
}

check_body_contains() {
  local description=$1
  local url=$2
  local expected_text=$3
  shift 3

  echo "Checking ${description}: ${url}"
  local body
  body=$(curl_cmd --fail --silent --show-error "$@" "${url}")
  if ! grep -Fq "${expected_text}" <<<"${body}"; then
    echo "Expected response marker '${expected_text}' was not found for ${description}" >&2
    exit 1
  fi
}

check_page_contains() {
  local description=$1
  local url=$2
  local expected_text=$3
  shift 3

  echo "Checking ${description}: ${url}"
  local page
  page=$(curl_cmd --fail --silent --show-error "$@" "${url}")
  if ! grep -Fq "${expected_text}" <<<"${page}"; then
    echo "Expected page marker '${expected_text}' was not found for ${description}" >&2
    exit 1
  fi
}

check_page_contains_any() {
  local description=$1
  local url=$2
  local expected_text_a=$3
  local expected_text_b=$4
  shift 4

  echo "Checking ${description}: ${url}"
  local page
  page=$(curl_cmd --fail --silent --show-error "$@" "${url}")
  if ! grep -Fq "${expected_text_a}" <<<"${page}" && ! grep -Fq "${expected_text_b}" <<<"${page}"; then
    echo "Expected page markers '${expected_text_a}' or '${expected_text_b}' were not found for ${description}" >&2
    exit 1
  fi
}

check_page_excludes() {
  local description=$1
  local url=$2
  local unexpected_text=$3
  shift 3

  echo "Checking ${description} does not contain fallback marker: ${url}"
  local page
  page=$(curl_cmd --fail --silent --show-error "$@" "${url}")
  if grep -Fq "${unexpected_text}" <<<"${page}"; then
    echo "Unexpected page marker '${unexpected_text}' was found for ${description}" >&2
    exit 1
  fi
}

echo "== Backend health =="
check_json "healthz" "${API_ORIGIN}/healthz"
check_json "readyz" "${API_ORIGIN}/readyz"
check_json "listing sources" "${API_ORIGIN}/api/listings/sources" "${auth[@]}"
check_body_contains "listing sources contain real automated source" "${API_ORIGIN}/api/listings/sources" "${REAL_SOURCE_KEY}" "${auth[@]}"
check_json "backend listings" "${API_ORIGIN}/api/listings?source=${REAL_SOURCE_KEY}"
check_json "backend listing clusters" "${API_ORIGIN}/api/listing-clusters"
check_json "backend sites" "${API_ORIGIN}/api/sites"
check_json "backend opportunities" "${API_ORIGIN}/api/opportunities/"

echo "== App proxy auth =="
app_auth_email=$(resolve_app_auth_email) || {
  echo "APP_AUTH_EMAIL is required for non-local app smoke checks." >&2
  exit 1
}
app_auth_password=$(resolve_app_auth_password) || {
  echo "APP_AUTH_PASSWORD is required for non-local app smoke checks." >&2
  exit 1
}
login_status=$(
  curl_cmd --silent --show-error --output /dev/null --dump-header "${login_headers}" --write-out '%{http_code}' \
    --cookie-jar "${cookie_jar}" \
    --data-urlencode "email=${app_auth_email}" \
    --data-urlencode "password=${app_auth_password}" \
    --data-urlencode "next=/review-queue" \
    -X POST \
    "${APP_ORIGIN}/api/auth/login"
)
case "${login_status}" in
  302|303)
    login_location=$(awk 'tolower($1) == "location:" {print $2}' "${login_headers}" | tr -d '\r')
    case "${login_location}" in
      */review-queue|/review-queue)
        echo "App login succeeded with redirect ${login_status} to ${login_location}"
        ;;
      *)
        echo "App login redirected to unexpected location: ${login_location:-<missing>}" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "App login failed with status ${login_status}" >&2
    exit 1
    ;;
esac

echo "== Protected app-proxy surfaces =="
check_json "data health" "${APP_ORIGIN}/api/health/data" --cookie "${cookie_jar}"
check_json "model health" "${APP_ORIGIN}/api/health/model" --cookie "${cookie_jar}"
check_json "review queue" "${APP_ORIGIN}/api/admin/review-queue" --cookie "${cookie_jar}"
check_json "listings proxy" "${APP_ORIGIN}/api/listings" --cookie "${cookie_jar}"
check_json "listing clusters proxy" "${APP_ORIGIN}/api/listing-clusters" --cookie "${cookie_jar}"
check_json "sites proxy" "${APP_ORIGIN}/api/sites" --cookie "${cookie_jar}"
check_json "opportunities proxy" "${APP_ORIGIN}/api/opportunities" --cookie "${cookie_jar}"
check_json "listing sources proxy" "${APP_ORIGIN}/api/listings/sources" --cookie "${cookie_jar}"
check_json "admin jobs proxy" "${APP_ORIGIN}/api/admin/jobs" --cookie "${cookie_jar}"
check_body_contains "listing sources proxy contains real automated source" "${APP_ORIGIN}/api/listings/sources" "${REAL_SOURCE_KEY}" --cookie "${cookie_jar}"
check_body_contains "admin jobs proxy contains connector runs" "${APP_ORIGIN}/api/admin/jobs" "LISTING_SOURCE_RUN" --cookie "${cookie_jar}"
check_json "proxy listings" "${APP_ORIGIN}/api/listings?source=${REAL_SOURCE_KEY}" --cookie "${cookie_jar}"
check_json "proxy listing clusters" "${APP_ORIGIN}/api/listing-clusters" --cookie "${cookie_jar}"
check_json "proxy sites" "${APP_ORIGIN}/api/sites" --cookie "${cookie_jar}"
check_json "proxy opportunities" "${APP_ORIGIN}/api/opportunities" --cookie "${cookie_jar}"

echo "== Authenticated frontend pages =="
check_page_contains \
  "listings page" \
  "${APP_ORIGIN}/listings" \
  "Listing intake ledger" \
  --cookie "${cookie_jar}"
check_page_contains_any \
  "listings page live-data marker" \
  "${APP_ORIGIN}/listings" \
  "Live API rows in the current query" \
  "Live API returned zero rows for the current query" \
  --cookie "${cookie_jar}"
check_page_excludes \
  "listings page" \
  "${APP_ORIGIN}/listings" \
  "Local fallback rows in the current query" \
  --cookie "${cookie_jar}"
check_page_contains \
  "source runs page" \
  "${APP_ORIGIN}/admin/source-runs" \
  "Connector run console" \
  --cookie "${cookie_jar}"
check_page_contains \
  "source runs page live-data marker" \
  "${APP_ORIGIN}/admin/source-runs" \
  "Live API" \
  --cookie "${cookie_jar}"
check_page_contains \
  "cluster page" \
  "${APP_ORIGIN}/listing-clusters" \
  "Cluster review queue" \
  --cookie "${cookie_jar}"
check_page_contains \
  "sites page" \
  "${APP_ORIGIN}/sites" \
  "Site registry" \
  --cookie "${cookie_jar}"
check_page_contains \
  "opportunities page" \
  "${APP_ORIGIN}/opportunities" \
  "Planning-first opportunity queue" \
  --cookie "${cookie_jar}"

echo "== Frontend reachability =="
app_status=$(curl_cmd --silent --show-error --output /dev/null --write-out '%{http_code}' "${APP_ORIGIN}")
case "${app_status}" in
  200|307|308|401|403)
    echo "Frontend reachable with status ${app_status}"
    ;;
  *)
    echo "Unexpected frontend status: ${app_status}" >&2
    exit 1
    ;;
esac

head_status=$(curl_cmd --silent --show-error --output /dev/null --write-out '%{http_code}' --head "${APP_ORIGIN}")
case "${head_status}" in
  200|307|308|401|403)
    echo "Frontend HEAD reachable with status ${head_status}"
    ;;
  *)
    echo "Unexpected frontend HEAD status: ${head_status}" >&2
    exit 1
    ;;
esac

echo "Production smoke checks passed."
