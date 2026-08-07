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
| `RECALLUM__TELEMETRY__BATCH_SIZE` | `100` | Pending tool events written per database batch |
| `RECALLUM__TELEMETRY__FLUSH_INTERVAL_SECONDS` | `5` | Maximum delay before pending activity is flushed |
| `RECALLUM__TELEMETRY__BUFFER_LIMIT` | `1000` | Maximum in-memory events; overflow drops the oldest |
| `RECALLUM__TELEMETRY__RETENTION_DAYS` | `90` | Age after which persisted activity is purged |
| `RECALLUM__LIMITS__*` | see `src/recallum/config.py` | Content/metadata/retrieval limits |

The telemetry buffer must be at least as large as its batch. Tool calls enqueue
only content-free metadata in memory; one lifecycle-owned worker performs batch
writes and periodic retention purges. An orderly shutdown attempts a final
flush. A process crash or prolonged database outage may lose the oldest pending
events by design and never prevents an MCP tool call from completing.

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

Alembic owns the schema. The application never runs `create_all()`. The image's
entrypoint (`deploy/entrypoint.sh`) runs `alembic upgrade head` and then `exec`s
the server, so **every** way of starting the container migrates first — compose,
Dokploy, or a bare `docker run`. Nothing to remember per deployment.

If migrations fail, the entrypoint retries (`RECALLUM_MIGRATION_ATTEMPTS`,
default 10, `RECALLUM_MIGRATION_RETRY_SECONDS` apart) to absorb a database that
is not accepting connections yet, then **exits non-zero rather than serving**
against an unexpected schema.

Inspect or run migrations by hand against a running stack:

```bash
docker compose exec recallum uv run --no-sync alembic current
```

The image has **no `CMD`** — the entrypoint runs the server itself, so there is
nothing for a stray "run command" to replace. One-off commands therefore go
through `exec` (which bypasses the entrypoint) rather than `docker run`:

```bash
docker compose exec recallum uv run --no-sync recallum-admin list-keys --email you@example.com
```

Serve without migrating, to debug a container whose database is unreachable or
mid-restore:

```bash
docker run --rm -e RECALLUM_SKIP_MIGRATIONS=1 <image>
```

**One replica at a time for schema-changing deploys.** Concurrent boots both
migrating is not serialized by an advisory lock; the loser fails, retries, and
finds the schema already at head, so it self-heals — but a rolling deploy across
replicas is noisier than it needs to be. Scale to 1 while a migration lands.

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

**3. Migrations: nothing to configure.** The image migrates before it serves
(see "Migrations" above), inside the Recallum container as the `recallum` role,
idempotently on every deploy.

> **Leave Dokploy's *Run Command* (Advanced tab) completely empty — both the
> `Command` field and every `Args` row.** Despite its label ("run a custom
> command in the container after the application initialized") it does not run
> alongside or after the server: on Swarm those two fields are `ContainerSpec`
> `Command` and `Args`, which override the image's **entrypoint** and command
> respectively. A value there therefore bypasses `deploy/entrypoint.sh`
> entirely, skipping the migration *and* the server.
>
> Setting it to `uv run --no-sync alembic upgrade head` makes the container
> migrate, exit **0**, and be restarted forever while nothing ever listens on
> 8000. Traefik then has no upstream, every route answers 502, and because a 502
> carries no `Access-Control-Allow-Origin` the browser reports it as a CORS
> failure — sending you after a CORS bug that does not exist.

**4. Pull the embedding model** into the Ollama app's volume once (see
"Embedding model" above), then verify `/readyz` returns `ready`.

Deploy order: **postgres → role SQL (step 1) → ollama (+ model pull) → recallum
(its entrypoint migrates, then Granian starts)**.

## Changing the embedding model

Vectors from different models share no coordinate space, so after changing
`RECALLUM__OLLAMA__MODEL` the vector search leg ignores rows embedded by the
old model (they remain reachable through full-text search). Restore their
vector reach by re-embedding in place:

```bash
docker compose exec recallum uv run --no-sync recallum-admin reembed --all-users
```

The command is idempotent and resumable: rows whose embedding fails are
counted, skipped, and picked up on the next run. `/admin/status` reports
`model_mismatch: true` while any active row still carries stale provenance.

## Measuring retrieval quality

`recallum-admin eval` replays a golden dataset (a small corpus plus queries
with expected results) through the ordinary remember/recall paths and reports
MRR and recall@k per query tag (semantic, exact, typo, identifier, plus the
four language tags below), so the fusion tunables become measured choices
instead of defaults:

```bash
docker compose exec recallum uv run --no-sync recallum-admin eval \
  --email eval@example.com --dataset scripts/eval_dataset.json
```

Use a dedicated user for the corpus. Reseeding is idempotent (exact dedup), so
only *removing* or *rewording* a corpus row strands its previously seeded
memory: the row stays active but no longer maps to a key, and competes for
top-k slots as an unlabelled distractor. Adding rows, or changing a row's
importance or category, strands nothing — those reseed onto the same memory.
You do not have to prune preemptively: a stranded row shows up as `?<id>` in
the `misses:` section of the report, so prune when you see one. Grow the dataset
with real queries agents got wrong: every fixed regression should leave a
query behind. `--trigram-weight` / `--importance-weight` override one knob for
an A/B run; numbers are only comparable against the same dataset and the same
embedding model. Persist a winning value via the `RECALLUM__LIMITS__*`
environment variables.

### Reading the language tags

Memories are written in English on purpose: dedup is an exact content hash and
`content_tsv` uses the English text-search configuration, so one fact stored in
two languages becomes two memories that no single query retrieves. The dataset
measures what that policy costs with a 2×2 — each fact is stored once and
queried in both languages, so the language is the only variable:

| tag | stored | queried | what a low score means |
| --- | --- | --- | --- |
| `en-en` | English | English | the policy itself is not paying off |
| `es-es` | Spanish | Spanish | pre-policy control; the baseline to beat |
| `es-en` | Spanish | English | pre-policy memories are unreachable — the migration is urgent |
| `en-es` | English | Spanish | half-compliance is expensive — agents must translate queries too |

`en-es` is the one to watch. Storing English while still querying in the user's
language drops the full-text and trigram legs and leaves only the embedding
leg, which is worse than never having switched. If it sags, the instruction
reached the write path but not the read path.

Both cross-language tags are an **optimistic** bound: Spanish and English
technical vocabulary share Latin roots and the trigram leg is character-based,
so cognates hand those queries a partial lexical freebie that real mixed-language
traffic will not always get.

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

**Primary mechanism: Dokploy native scheduled backups (to S3).** Dokploy runs
`pg_dump` inside the managed database container and uploads to S3-compatible
storage. This matches the pg17 server, needs no PostgreSQL client on the host,
and works with the private-network topology (no published port required).

Prerequisites:
- The Recallum PostgreSQL is deployed as a Dokploy **Database** resource.
- An **S3-compatible bucket + credentials** (e.g. Cloudflare R2, Backblaze B2,
  MinIO, AWS S3). Dokploy native backups require an S3 destination.

Configure in Dokploy (exact labels vary by version):

1. **Settings → Destinations (S3):** add a destination with endpoint, bucket,
   region, access key, secret key.
2. **Database (postgres) → Backups:** add a schedule with
   - cron `0 3 * * *` (daily 03:00),
   - database `recallum`,
   - the destination from step 1 and a key prefix (e.g. `recallum/`),
   - enabled.
3. **Run a manual backup once** and confirm the object lands in the bucket.

Retention: set a lifecycle/expiry rule on the bucket (e.g. 14 days) or prune in
the destination.

**Verified restore drill (perform after first deploy and quarterly):**

1. Download the latest dump from S3 (or use Dokploy's restore action).
2. Restore into a scratch database, e.g. inside the pg container:
   `pg_restore -U recallum_admin -d recallum_verify --clean --if-exists <dump>`
   (create `recallum_verify` first with `createdb`).
3. Verify: `psql -d recallum_verify -c 'SELECT count(*) FROM users; SELECT count(*) FROM memories;'`
4. Spot-check one memory: `psql -d recallum_verify -c 'SELECT content FROM memories LIMIT 1;'`
5. Drop the scratch database.
6. Record date + result of the drill.

Physically purge old soft-deletes during maintenance (run inside the pg
container as `recallum_admin`):

```bash
docker exec <pg-container> psql -U recallum_admin -d recallum \
  -c "DELETE FROM memories WHERE deleted_at < now() - interval '30 days'"
```

### Alternative: self-hosted script backups (no S3)

If you prefer local dumps instead of Dokploy/S3, the repo ships
`scripts/backup_pg.sh`, `scripts/restore_pg.sh` and `scripts/purge_deleted.sh`.
They expect host-level `pg_dump`/`psql` (pg17) reaching the database, so with the
private-network topology run them via `docker exec` into the pg container. Cron
example:

```cron
15 3 * * * PGUSER=recallum_admin PGPASSWORD=... /opt/recallum/scripts/backup_pg.sh >> /var/log/recallum-backup.log 2>&1
```

Backups are private custom-format dumps (`0700` directory, `0600` files) in
`/opt/recallum/backups` with 14-day retention. Purge shared/moved backups first
with `./scripts/purge_deleted.sh 30`.

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
# Web access bootstrap

Web access is enabled on an existing user; it does not create a second identity:

```console
recallum-admin set-password --email operator@example.com
recallum-admin grant-admin --email operator@example.com
```

`set-password` reads and confirms the password interactively. Keep the UI and API
under the same registrable domain so `SameSite=Lax` credentials work (the default
pair is `memory.zozbit.com` and `recallum.zozbit.com`). The cookie remains host-only
and is limited to `/api/v1`.

Web settings use the standard nested environment convention:

- `RECALLUM__WEB__ALLOWED_ORIGIN` (default `https://memory.zozbit.com`)
- `RECALLUM__WEB__COOKIE_NAME` (default `recallum_session`)
- `RECALLUM__WEB__IDLE_SECONDS` (default 604800)
- `RECALLUM__WEB__ABSOLUTE_SECONDS` (default 2592000)
- `RECALLUM__WEB__ROTATION_THRESHOLD` (default 0.5)
- `RECALLUM__WEB__ARGON2_MEMORY_COST`, `ARGON2_TIME_COST`,
  `ARGON2_PARALLELISM`, `ARGON2_HASH_LEN`, and `ARGON2_SALT_LEN`

## Administration recovery and user removal

The web console is not the recovery boundary. If no usable administrator
session remains, run `recallum-admin set-password` and
`recallum-admin grant-admin` inside the application container for an existing
user.

User deletion is deliberately absent from the web API. Deleting a `users` row
cascades irreversibly into that person's memories and credentials; until there
is an export/deactivation workflow, withdraw access by revoking API keys (and
changing the web password from the CLI) without destroying content.
