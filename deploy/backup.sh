#!/usr/bin/env bash
set -euo pipefail

export PGPASSWORD="$(cat "${PGPASSWORD_FILE}")"
export AWS_ACCESS_KEY_ID="$(cat "${AWS_ACCESS_KEY_ID_FILE}")"
export AWS_SECRET_ACCESS_KEY="$(cat "${AWS_SECRET_ACCESS_KEY_FILE}")"
LOCAL_REPOSITORY=/backups/restic
INTERVAL="${OMNILIT_BACKUP_INTERVAL_SECONDS:-86400}"
KEEP_DAILY="${OMNILIT_BACKUP_KEEP_DAILY:-14}"

initialize_repository() {
  local repository="$1"
  if ! restic -r "$repository" snapshots >/dev/null 2>&1; then
    restic -r "$repository" init
  fi
}

while true; do
  started="$(date -u +%Y%m%dT%H%M%SZ)"
  dump="/tmp/omnilit-${started}.dump"
  pg_dump --format=custom --no-owner --no-privileges --file="$dump"
  initialize_repository "$LOCAL_REPOSITORY"
  restic -r "$LOCAL_REPOSITORY" backup "$dump" /objects/private /objects/public --tag omnilit
  restic -r "$LOCAL_REPOSITORY" forget --keep-daily "$KEEP_DAILY" --prune
  initialize_repository "$OMNILIT_S3_REPOSITORY"
  restic -r "$OMNILIT_S3_REPOSITORY" copy --from-repo "$LOCAL_REPOSITORY"
  restic -r "$OMNILIT_S3_REPOSITORY" forget --keep-daily "$KEEP_DAILY" --prune
  rm -f "$dump"
  sleep "$INTERVAL"
done
