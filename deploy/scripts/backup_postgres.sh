#!/usr/bin/env bash
# Dumps the app's Postgres database and prunes old local backups.
#
# Requires: pg_dump (the postgresql-client package — a separate install
# from the app's own Python venv), and DATABASE_URL set to the same
# connection string the app uses.
#
# Managed Postgres hosts (RDS, Supabase, Neon, Fly Postgres, etc.) already
# do this for you automatically — this script is only for a self-managed
# Postgres instance. Run it via deploy/systemd/cs61a-postgres-backup.{service,timer}.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/cs61a-discussion}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
DUMP_FILE="$BACKUP_DIR/cs61a-discussion-${TIMESTAMP}.dump"

# --format=custom: compressed and restorable with pg_restore (including
# selective table restores), unlike a plain SQL dump.
pg_dump --format=custom --file="$DUMP_FILE" "$DATABASE_URL"
echo "Backed up to $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))"

# Optional off-site copy. A backup that lives only on the same host as the
# database it's backing up doesn't protect against losing that host
# outright — configure this (or your own equivalent) before relying on it.
if [[ -n "${BACKUP_S3_BUCKET:-}" ]] && command -v aws >/dev/null 2>&1; then
    aws s3 cp "$DUMP_FILE" "s3://${BACKUP_S3_BUCKET}/$(basename "$DUMP_FILE")"
    echo "Copied to s3://${BACKUP_S3_BUCKET}/$(basename "$DUMP_FILE")"
fi

find "$BACKUP_DIR" -name 'cs61a-discussion-*.dump' -mtime "+${RETENTION_DAYS}" -delete
