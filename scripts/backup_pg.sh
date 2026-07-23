#!/usr/bin/env bash
# Daily PostgreSQL backup (custom-format dump, compressed).
# Intended for a VPS cron entry, e.g.:
#   15 3 * * * /opt/recallum/scripts/backup_pg.sh >> /var/log/recallum-backup.log 2>&1
# Requires pg_dump (PostgreSQL client tools) and the env vars below.
set -euo pipefail
umask 077

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-recallum_admin}"
PGDATABASE="${PGDATABASE:-recallum}"
BACKUP_DIR="${BACKUP_DIR:-/opt/recallum/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
# PGPASSWORD is read by pg_dump from the environment.

admin=$(psql -Atqc "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
[[ "$admin" == "t" ]] || { echo "backup requires a PostgreSQL admin/BYPASSRLS role" >&2; exit 1; }

install -d -m 0700 "$BACKUP_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
out="$BACKUP_DIR/recallum-$stamp.dump"

pg_dump --format=custom --compress=6 --file="$out"
chmod 0600 "$out"

# Prune old backups.
find "$BACKUP_DIR" -name 'recallum-*.dump' -mtime +"$RETENTION_DAYS" -delete

echo "backup complete: $out"
