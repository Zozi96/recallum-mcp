#!/usr/bin/env bash
# Restore a Recallum PostgreSQL dump (inverse of backup_pg.sh).
# Usage: restore_pg.sh /path/to/recallum-YYYYmmdd-HHMMSS.dump target_db
#
# Verification procedure (run before trusting any backup strategy):
#   1. Restore into a scratch database: restore_pg.sh <dump> recallum_verify
#   2. Check row counts: psql -d recallum_verify -c 'SELECT count(*) FROM memories;'
#   3. Drop the scratch database: psql -c 'DROP DATABASE recallum_verify;'
set -euo pipefail

dump_file="${1:?usage: restore_pg.sh <dump-file> <target_db>}"
target_db="${2:?usage: restore_pg.sh <dump-file> <target_db>}"
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-recallum_admin}"

pg_restore --list "$dump_file" >/dev/null
admin=$(psql -Atqc "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
[[ "$admin" == "t" ]] || { echo "restore requires a PostgreSQL admin/BYPASSRLS role" >&2; exit 1; }

echo "restoring $dump_file into database '$target_db' on $PGHOST:$PGPORT"
pg_restore --dbname="$target_db" --clean --if-exists --single-transaction \
  --no-owner --no-privileges "$dump_file"
echo "restore complete"
