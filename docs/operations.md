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

**Important:** the application database user must be a regular role, never a
superuser or BYPASSRLS role — superusers bypass Row-Level Security. The
migrations may run as a privileged role; the runtime `RECALLUM__DATABASE__URL`
should not.

## Migrations

Alembic owns the schema. The application never runs `create_all()`.

```bash
# From the repo (or an image with the same env var):
RECALLUM__DATABASE__URL="postgresql+asyncpg://..." uv run alembic upgrade head
uv run alembic current    # verify: 0001_initial_schema (head)
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
- `GET /readyz` — readiness, checks PostgreSQL (`SELECT 1`) and Ollama
  (`/api/version`); 200 `ready` or 503 `unavailable` with per-check status.
  Never includes credentials or memory data.

## Backups and verified restore

Daily backups via cron (`scripts/backup_pg.sh`):

```cron
15 3 * * * PGPASSWORD=... /opt/recallum/scripts/backup_pg.sh >> /var/log/recallum-backup.log 2>&1
```

Backups are custom-format dumps in `/opt/recallum/backups` with 14-day
retention. Restore with `scripts/restore_pg.sh`.

**Verified restore drill (perform after first deploy and quarterly):**

1. `PGPASSWORD=... ./scripts/restore_pg.sh <latest-dump> recallum_verify`
2. `psql -d recallum_verify -c 'SELECT count(*) FROM users; SELECT count(*) FROM memories;'`
3. Spot-check one memory: `psql -d recallum_verify -c 'SELECT content FROM memories LIMIT 1;'`
4. `psql -c 'DROP DATABASE recallum_verify;'`
5. Record date + result of the drill.

Before restoring a backup that will be shared or moved, run a physical purge
of logically-deleted rows first (design constraint: soft-deletes stay on disk
until maintenance).

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
