#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/backup_storage.sh <output_dir>

Required environment variables:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SUPABASE_STORAGE_BUCKET

Dependencies:
  curl
  jq
EOF
}

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required." >&2
  exit 1
fi

: "${SUPABASE_URL:?SUPABASE_URL is required}"
: "${SUPABASE_SERVICE_ROLE_KEY:?SUPABASE_SERVICE_ROLE_KEY is required}"
: "${SUPABASE_STORAGE_BUCKET:?SUPABASE_STORAGE_BUCKET is required}"

OUTPUT_ROOT=$1
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_DIR="${OUTPUT_ROOT%/}/supabase-storage-${TIMESTAMP}"
MANIFEST_JSONL=$(mktemp)
mkdir -p "${BACKUP_DIR}"

cleanup() {
  rm -f "${MANIFEST_JSONL}"
}
trap cleanup EXIT

auth_headers=(
  -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}"
  -H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}"
)

list_prefix() {
  local prefix=$1
  local offset=0
  local page_size=1000
  local response items_count

  while true; do
    response=$(curl --fail --silent --show-error \
      -X POST \
      "${SUPABASE_URL%/}/storage/v1/object/list/${SUPABASE_STORAGE_BUCKET}" \
      "${auth_headers[@]}" \
      -H "Content-Type: application/json" \
      --data "$(jq -nc \
        --arg prefix "${prefix}" \
        --argjson limit "${page_size}" \
        --argjson offset "${offset}" \
        '{prefix: $prefix, limit: $limit, offset: $offset, sortBy: {column: "name", order: "asc"}}')"
    )

    items_count=$(jq 'length' <<<"${response}")
    if [[ "${items_count}" -eq 0 ]]; then
      break
    fi

    while IFS=$'\t' read -r entry_type name size updated_at; do
      if [[ -z "${name}" ]]; then
        continue
      fi

      if [[ "${entry_type}" == "dir" ]]; then
        list_prefix "${prefix}${name}/"
        continue
      fi

      local object_path="${prefix}${name}"
      local destination="${BACKUP_DIR}/${object_path}"

      mkdir -p "$(dirname "${destination}")"
      curl --fail --silent --show-error \
        "${SUPABASE_URL%/}/storage/v1/object/${SUPABASE_STORAGE_BUCKET}/${object_path}" \
        "${auth_headers[@]}" \
        --output "${destination}"

      jq -nc \
        --arg path "${object_path}" \
        --arg updated_at "${updated_at}" \
        --argjson size_bytes "${size}" \
        '{
          path: $path,
          size_bytes: $size_bytes,
          updated_at: ($updated_at | select(length > 0))
        }' >>"${MANIFEST_JSONL}"
    done < <(
      jq -r '
        .[]
        | [
            (if (.id == null or .metadata == null) then "dir" else "file" end),
            .name,
            ((.metadata.size // 0) | tonumber),
            (.updated_at // "")
          ]
        | @tsv
      ' <<<"${response}"
    )

    if [[ "${items_count}" -lt "${page_size}" ]]; then
      break
    fi
    offset=$((offset + page_size))
  done
}

list_prefix ""

MANIFEST_PATH="${BACKUP_DIR}/manifest.json"
jq -sc \
  --arg bucket "${SUPABASE_STORAGE_BUCKET}" \
  --arg exported_at "${TIMESTAMP}" \
  '{
    bucket: $bucket,
    exported_at: $exported_at,
    object_count: length,
    objects: .
  }' "${MANIFEST_JSONL}" >"${MANIFEST_PATH}"

echo "Storage backup complete: ${BACKUP_DIR}"
echo "Manifest: ${MANIFEST_PATH}"
