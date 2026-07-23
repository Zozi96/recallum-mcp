# Recallum Operations

Deployment and maintenance runbook for the VPS (Ubuntu 24.04, Docker, Dokploy, Traefik).

## Services and resource limits

| Service    | Image                    | Memory limit | Exposure       |
|------------|--------------------------|--------------|----------------|
| recallum   | `recallum:latest` (deploy/Dockerfile) | 512 MiB | HTTPS only, via Traefik |
| postgres   | `pgvector/pgvector:pg17` | 2 GiB        | private network only |
| ollama     | `ollama/ollama:latest`   | 1.5 GiB      | private network only |

PostgreSQL and Ollama never publish ports; they are reachable only from the
private compose/Dokploy network. See `deploy/dokploy-compose.yml` for the
Traefik labels (adjust the `Host(...)` rule).

## Embedding model (persistent download)

The embedding model lives on the Ollama volume and survives container
recreation:

```bash
docker compose exec ollama ollama pull embeddinggemma:300m-qat-q4_0
docker compose exec ollama ollama list   # verify
```

The volume mount `/root/.ollama` (compose: `ollama` / Dokploy:
`recallum-ollama`) keeps the model across upgrades. Recallum expects 768-dim
vectors; `embeddinggemma:300m-qat-q4_0` provides exactly that and runs on CPU
within the 1.5 GiB limit.

## Environment variables

All settings use `RECALLUM__<GROUP>__<FIELD>`:

| Variable | Default | Purpose |
|---|---|---|
| `RECALLUM__DATABASE__URL` | `postgresql+asyncpg://recallum:recallum@localhost:5432/recallum` | Async PostgreSQL DSN (asyncpg driver) |
| `RECALLUM__DATABASE__ECHO` | `false` | SQL statement logging |
| `RECALLUM__DATABASE__POOL_SIZE` | `5` | Connection pool size |
| `RECALLUM__DATABASE__MAX_OVERFLOW` | `5` | Pool overflow |
| `RECALLUM__OLLAMA__URL` | `http://localhost:11434` | Ollama base URL |
| `RECALLUM__OLLAMA__MODEL` | `embeddinggemma:300m-qat-q4_0` | Embedding model |
| `RECALLUM__OLLAMA__TIMEOUT_SECONDS` | `30` | Embedding timeout |
| `RECALLUM__AUTH__KEY_PREFIX` | `rcl_` | API key prefix |
| `RECALLUM__LIMITS__*` | see `src/recallum/config.py` | Content/metadata/retrieval limits |

**Important:** the application database user owns Recallum's tables but must
never be a superuser or have `BYPASSRLS`. On a fresh volume,
`deploy/postgres-init/10-secure-runtime-role.sh` installs pgvector and creates
that role separately from `recallum_admin`. For an existing volume originally
created with `POSTGRES_USER=recallum`, first create a separate superuser admin,
then demote the runtime role before deploying this version:

```sql
CREATE ROLE recallum_admin LOGIN SUPERUSER PASSWORD 'replace-me';
ALTER ROLE recallum NOSUPERUSER NOBYPASSRLS;
```

## Migrations

Alembic owns the schema. The application never runs `create_all()`. Compose
runs the one-shot `migrate` service before starting Recallum.

```bash
docker compose run --rm migrate
docker compose run --rm migrate uv run --no-sync alembic current
```

## Users and API keys

```bash
uv run recallum-admin create-user --email zozi@example.com
uv run recallum-admin issue-key --email zozi@example.com --name laptop   # printed ONCE
uv run recallum-admin list-keys --email zozi@example.com
uv run recallum-admin revoke-key --key-id <uuid>
```

## Health probes

- `GET /healthz` — liveness, no dependency checks, always 200 when the process runs.
- `GET /readyz` — readiness, checks the PostgreSQL schema, table ownership,
  runtime role safety and Ollama (`/api/version`); 200 `ready` or 503
  `unavailable` with per-check status.
  Never includes credentials or memory data.

## Backups and verified restore

Daily backups via cron (`scripts/backup_pg.sh`):

```cron
15 3 * * * PGUSER=recallum_admin PGPASSWORD=... /opt/recallum/scripts/backup_pg.sh >> /var/log/recallum-backup.log 2>&1
```

Backups are private custom-format dumps (`0700` directory, `0600` files) in
`/opt/recallum/backups` with 14-day retention. Restore only into an explicit
target database with `scripts/restore_pg.sh`.

**Verified restore drill (perform after first deploy and quarterly):**

1. `createdb recallum_verify`
2. `PGUSER=recallum_admin PGPASSWORD=... ./scripts/restore_pg.sh <latest-dump> recallum_verify`
3. `psql -d recallum_verify -c 'SELECT count(*) FROM users; SELECT count(*) FROM memories;'`
4. Spot-check one memory: `psql -d recallum_verify -c 'SELECT content FROM memories LIMIT 1;'`
5. `dropdb recallum_verify`
6. Record date + result of the drill.

Physically purge old soft-deletes during maintenance, and before creating a
backup that will be shared or moved:

```bash
PGUSER=recallum_admin PGPASSWORD=... ./scripts/purge_deleted.sh 30
```

## Rollback

1. Remove the Traefik route (or disable the router label) for Recallum.
2. Redeploy the previous Recallum image tag.
3. Migrations are additive; volumes are preserved — rollback never deletes data.

## Post-deploy smoke test

```bash
RECALLUM_URL=https://recallum.example.com \
ALICE_KEY=rcl_... BOB_KEY=rcl_... \
./scripts/smoke_test.sh
```
