#!/usr/bin/env bash
# Permanently delete memories soft-deleted more than the requested days ago.
set -euo pipefail

days="${1:?usage: purge_deleted.sh <days>}"
[[ "$days" =~ ^[1-9][0-9]*$ ]] || { echo "days must be a positive integer" >&2; exit 2; }
PGUSER="${PGUSER:-recallum_admin}"

admin=$(psql -Atqc "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
[[ "$admin" == "t" ]] || { echo "purge requires a PostgreSQL admin/BYPASSRLS role" >&2; exit 1; }

psql --set=ON_ERROR_STOP=1 --set=days="$days" <<'SQL'
BEGIN;
DELETE FROM memories
WHERE deleted_at < now() - make_interval(days => :'days'::integer);
COMMIT;
SQL
