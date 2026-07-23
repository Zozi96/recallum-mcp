#!/usr/bin/env bash
set -euo pipefail

app_user="${RECALLUM_APP_USER:?set RECALLUM_APP_USER}"
app_password="${RECALLUM_APP_PASSWORD:?set RECALLUM_APP_PASSWORD}"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_user="$app_user" --set=app_password="$app_password" \
  --set=database="$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS;
ALTER DATABASE :"database" OWNER TO :"app_user";
ALTER SCHEMA public OWNER TO :"app_user";
SQL
