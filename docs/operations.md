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

On Dokploy with separate services (no `migrate` container), migrations run as a
**pre-deploy command** instead — see below.

## Dokploy deployment (separate services)

Each piece is its own Dokploy resource on the shared external `dokploy-network`
(no monolithic compose). Only Recallum gets a public domain; PostgreSQL and
Ollama stay private with no published ports.

| Resource | Type | Image | Domain | Memory |
|---|---|---|---|---|
| postgres | Database | `pgvector/pgvector:pg17` (override the default!) | none | 2 GiB |
| ollama | Application (Docker) | `ollama/ollama:latest`, volume `/root/.ollama` | none | 1.5 GiB |
| recallum | Application (this repo's `deploy/Dockerfile`) | built | HTTPS via Traefik, port 8000 | 512 MiB |

Reference each service by the **internal host Dokploy shows** for it (they share
`dokploy-network`); never hardcode IPs.

**1. Create the runtime role once.** Dokploy's managed database does not run
`deploy/postgres-init/10-secure-runtime-role.sh`, so run its SQL by hand
(connected as the admin `recallum_admin` to database `recallum`). Readiness
(`/readyz`) stays `unavailable` until this exists, because it verifies the
connecting role is non-superuser, has no `BYPASSRLS`, and owns the tables:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE recallum LOGIN PASSWORD 'CHANGE_ME_APP' NOSUPERUSER NOBYPASSRLS;
ALTER DATABASE recallum OWNER TO recallum;
ALTER SCHEMA public OWNER TO recallum;
```

**2. Recallum environment** (connect as the `recallum` app role, **never**
`recallum_admin` — the admin is a superuser and would fail readiness):

```
RECALLUM__DATABASE__URL=postgresql+asyncpg://recallum:CHANGE_ME_APP@<pg-internal-host>:5432/recallum
RECALLUM__OLLAMA__URL=http://<ollama-internal-host>:11434
```

**3. Migrations = pre-deploy command (option A).** The image never migrates on
build or start (the Dockerfile `CMD` only runs uvicorn). Configure Recallum's
**pre-deploy command** in Dokploy so Alembic runs after the image is built and
the database is reachable, but before the server starts:

```bash
uv run --no-sync alembic upgrade head
```

This runs inside the Recallum container as the `recallum` role (so tables are
owned by it), is idempotent (safe to re-run every deploy), and does not touch
`docker build`. If your Dokploy version lacks a pre-deploy hook, run the same
command once via the container terminal before sending traffic.

**4. Pull the embedding model** into the Ollama app's volume once (see
"Embedding model" above), then verify `/readyz` returns `ready`.

Deploy order: **postgres → role SQL (step 1) → ollama (+ model pull) → recallum
(pre-deploy migration runs, then uvicorn starts)**.

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

## Post-deploy smoke test (task 6.6)

`scripts/smoke_test.sh` drives the live endpoint over HTTP/JSON-RPC (`curl`
only) and asserts six things: liveness, readiness, an authenticated MCP
`remember`, rejection of missing/invalid tokens, isolation between two users,
and that the session still works. Run it after every deploy.

Prerequisites: the stack is up and `GET /readyz` reports `ready` (which
requires the Ollama model already pulled — see "Embedding model" above).

**1. Create two fresh users and issue their keys** (each secret is printed once):

```bash
docker compose exec recallum uv run recallum-admin create-user --email alice@smoke.test
docker compose exec recallum uv run recallum-admin issue-key   --email alice@smoke.test --name smoke
docker compose exec recallum uv run recallum-admin create-user --email bob@smoke.test
docker compose exec recallum uv run recallum-admin issue-key   --email bob@smoke.test --name smoke
```

> Use **fresh** users. Check #5 asserts Bob sees `"total":0`, so reusing a Bob
> that already has memories will fail the isolation check.

**2. Run the smoke test** with the two `rcl_...` secrets from step 1:

```bash
RECALLUM_URL=https://recallum.example.com \
ALICE_KEY=rcl_<alice> \
BOB_KEY=rcl_<bob> \
  ./scripts/smoke_test.sh
```

Expected final line: `smoke test OK`.

**3. Clean up the test keys** (optional):

```bash
docker compose exec recallum uv run recallum-admin list-keys  --email alice@smoke.test
docker compose exec recallum uv run recallum-admin revoke-key --key-id <uuid>
# repeat for bob@smoke.test
```
