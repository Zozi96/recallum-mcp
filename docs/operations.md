# Recallum Operations

Deployment and maintenance runbook for the VPS (Ubuntu 24.04, Docker, Dokploy, Traefik).

## Services and resource limits

| Service    | Image                    | Memory limit | Exposure       |
|------------|--------------------------|--------------|----------------|
| recallum   | `recallum:1.0.0` (deploy/Dockerfile) | 512 MiB | HTTPS only, via Traefik |
| postgres   | `pgvector/pgvector:pg17` | 2 GiB        | private network only |
| ollama     | `ollama/ollama:0.12.6`   | 1.5 GiB      | private network only |

PostgreSQL and Ollama never publish ports; they are reachable only from the
private compose/Dokploy network. See `deploy/dokploy-compose.yml` for the
Traefik labels (adjust the `Host(...)` rule).

## Image update policy

Deploy images are pinned to immutable references in `deploy/Dockerfile`
(`python:3.14-slim` by digest) and in `deploy/docker-compose.yml` /
`deploy/dokploy-compose.yml` (`pgvector/pgvector:pg17` by digest comment,
`ollama/ollama:0.12.6` by tag). No deploy reference uses `:latest`.

Bump procedure (deliberate, reviewed):

1. Check the upstream digest for the tag you want:
   `docker buildx imagetools inspect <image>:<tag>` → take the top-level
   `Digest:`.
2. Update the reference in the compose/Dockerfile, keeping a comment with the
   resolved tag/digest next to it.
3. Re-run the supported compose gate: `bash scripts/check_compose_supported.sh`
   plus `docker compose -f deploy/docker-compose.yml config` to confirm the
   pull succeeds.
4. Merge via PR so the bump is reviewed like any other change.

Cadence suggestion: review security-relevant digests monthly, and after any
upstream security advisory for Postgres, Ollama or the Python base image.

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
| `RECALLUM__TELEMETRY__METRICS_TOKEN` | empty | Operator token for `GET /metrics`; required off loopback (compose sets it) |
| `RECALLUM__RUNTIME__WORKERS` | `1` | Granian workers; must stay `1` while MCP is stateful |
| `RECALLUM__RUNTIME__MCP_STATELESS_HTTP` | `false` | Reserved flag only; does not unlock `workers > 1` until FastMCP is wired for stateless HTTP |
| `RECALLUM__LIMITS__*` | see `src/recallum/config.py` | Content/metadata/retrieval limits |

`RECALLUM__LIMITS__PROFILE_STATIC_MIN_IMPORTANCE` is still accepted so existing
deployments keep parsing. It is obsolete and has **no effect** on static
profile eligibility: static is preference/constraint only, with importance
used only to order those candidates.

The public MCP boundary is configured under `RECALLUM__BOUNDARY__*`. Set
`RECALLUM__ENVIRONMENT=production` only with explicit, non-wildcard JSON arrays
for hosts, origins, and trusted proxy networks; production startup rejects
missing or invalid values. The defaults below are the validated S004 seam and
are not enforcement by themselves:

| Variable | Default | Purpose |
|---|---:|---|
| `RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS` | `localhost`, `127.0.0.1`, `[::1]`, `testserver` | Exact MCP Host allowlist |
| `RECALLUM__BOUNDARY__MCP__ALLOWED_ORIGINS` | local HTTP origins | Exact MCP Origin allowlist |
| `RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS` | `[]` | Peers allowed to supply `X-Forwarded-For` |
| `RECALLUM__BOUNDARY__REQUEST__GENERAL_BODY_BYTES` | `1048576` | General body ceiling |
| `RECALLUM__BOUNDARY__REQUEST__LOGIN_BODY_BYTES` | `16384` | Login body ceiling |
| `RECALLUM__BOUNDARY__REQUEST__PASSWORD_MAX_CHARS` | `256` | Password ceiling |
| `RECALLUM__BOUNDARY__RATE__*` | `30/300`, `5/300`, `60/60`, `10000` | Login IP, login IP-account, invalid MCP, and bucket budgets |

This VPS (Dokploy + Traefik on `dokploy-network`) uses the reviewed values
below. MCP `Host` is `recallum.zozbit.com`; the web UI origin is
`https://memory.zozbit.com`. Both hosts are allowlisted because Traefik may
present either name to the same app. Do not set
`RECALLUM__RUNTIME__MCP_STATELESS_HTTP` to unlock extra workers.

```bash
RECALLUM__ENVIRONMENT=production
RECALLUM__RUNTIME__WORKERS=1
RECALLUM__WEB__ALLOWED_ORIGIN=https://memory.zozbit.com
RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS='["recallum.zozbit.com","memory.zozbit.com"]'
RECALLUM__BOUNDARY__MCP__ALLOWED_ORIGINS='["https://recallum.zozbit.com","https://memory.zozbit.com"]'
RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS='["10.0.1.0/24"]'
RECALLUM__BOUNDARY__REQUEST__GENERAL_BODY_BYTES=1048576
RECALLUM__BOUNDARY__REQUEST__LOGIN_BODY_BYTES=16384
RECALLUM__BOUNDARY__REQUEST__PASSWORD_MAX_CHARS=256
RECALLUM__BOUNDARY__RATE__LOGIN_IP_ATTEMPTS=30
RECALLUM__BOUNDARY__RATE__LOGIN_IP_WINDOW_SECONDS=300
RECALLUM__BOUNDARY__RATE__LOGIN_ACCOUNT_ATTEMPTS=5
RECALLUM__BOUNDARY__RATE__LOGIN_ACCOUNT_WINDOW_SECONDS=300
RECALLUM__BOUNDARY__RATE__INVALID_MCP_AUTH_ATTEMPTS=60
RECALLUM__BOUNDARY__RATE__INVALID_MCP_AUTH_WINDOW_SECONDS=60
RECALLUM__BOUNDARY__RATE__MAX_BUCKETS=10000
```

The telemetry buffer must be at least as large as its batch. Tool calls enqueue
only content-free metadata in memory; one lifecycle-owned worker performs batch
writes and periodic retention purges. An orderly shutdown attempts a final
flush. A process crash or prolonged database outage may lose the oldest pending
events by design and never prevents an MCP tool call from completing.

## Operational metrics (`GET /metrics`)

`GET /metrics` is an operator-only JSON snapshot of in-memory process counters:
telemetry drops, flush failures, per-tool latency, degraded-recall ratio,
embedding-unavailable write ratio, and the current readiness probe results. It
is not an MCP tool, does not accept agent API keys, and never includes memory
content, user identifiers, queries, or tokens.

Access:

- Local compose still publishes Recallum on `127.0.0.1:8000` only, but the
  process sees the docker-bridge peer, not loopback. Set
  `RECALLUM__TELEMETRY__METRICS_TOKEN` (compose files include a placeholder).
- Dokploy/Traefik excludes `/metrics` from the public Host router; scrape on
  the private network with the same token.
- Loopback without a token is only the TCP peer (`request.client.host`).
  `X-Forwarded-For: 127.0.0.1` never grants access.
- Send `Authorization: Bearer <token>` or `X-Recallum-Metrics-Token: <token>`.
  An agent `rcl_…` key does not authorize this endpoint.

Counters are per process. `RECALLUM__RUNTIME__WORKERS` must stay `1`; multiple
workers would each expose a partial view with no aggregation.

```bash
curl -sS -H "Authorization: Bearer $RECALLUM__TELEMETRY__METRICS_TOKEN" \
  http://127.0.0.1:8000/metrics
```

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

For the profile-policy change (`0020_invalidate_memory_profiles`), do not mix
old and new workers: **stop every old Recallum process**, run the migration,
then start the new version. `0020` marks all `memory_profiles` rows
`generation=-1` (source memories and skills stay identical) so the first read
rebuilds under preference/constraint-only static. An old process left running
can rebuild a valid cache under the previous rule between migrate and start.

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

## Supported runtime topology (one worker, one replica)

Stateful MCP keeps sessions in process memory. The supported deployment is
exactly **one Granian worker** and **one replica**. `deploy/entrypoint.sh` and
typed `RuntimeSettings` both read `RECALLUM__RUNTIME__WORKERS` (default `1`):
the entrypoint refuses to start Granian when the value is not `1`, and Settings
rejects the same misconfiguration before traffic. Setting
`RECALLUM__RUNTIME__MCP_STATELESS_HTTP=true` does **not** unlock `workers > 1`
until FastMCP is actually wired for validated stateless HTTP.

Do not enable multi-worker or multi-replica serving until there is reviewed
evidence for one of:

1. FastMCP `stateless_http` (or equivalent) validated against Codex, Claude Code,
   and Cursor for initialize, tool calls, revocation mid-session, and reconnects;
2. Sticky sessions that pin every `/mcp` stream for a session to one process; or
3. Shared session state that every worker can read and write safely.

Capture that evidence in a change design and keep the one-worker entrypoint until
the suite lands. Dokploy compose is out of scope for this contract.

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
`recallum_admin` — the admin is a superuser and would fail readiness).
Production startup **rejects** the process unless the MCP allowlists, trusted
proxy CIDRs, request ceilings and rate budgets are all explicit. Set them on
the Recallum **Application** (not in `deploy/dokploy-compose.yml`). Clients
must use `https://recallum.zozbit.com/mcp/` — never configure `/mcp`.

```
RECALLUM__DATABASE__URL=postgresql+asyncpg://recallum:CHANGE_ME_APP@<pg-internal-host>:5432/recallum
RECALLUM__OLLAMA__URL=http://<ollama-internal-host>:11434
RECALLUM__ENVIRONMENT=production
RECALLUM__RUNTIME__WORKERS=1
RECALLUM__WEB__ALLOWED_ORIGIN=https://memory.zozbit.com
RECALLUM__BOUNDARY__MCP__ALLOWED_HOSTS=["recallum.zozbit.com","memory.zozbit.com"]
RECALLUM__BOUNDARY__MCP__ALLOWED_ORIGINS=["https://recallum.zozbit.com","https://memory.zozbit.com"]
RECALLUM__BOUNDARY__PROXY__TRUSTED_CIDRS=["10.0.1.0/24"]
RECALLUM__BOUNDARY__REQUEST__GENERAL_BODY_BYTES=1048576
RECALLUM__BOUNDARY__REQUEST__LOGIN_BODY_BYTES=16384
RECALLUM__BOUNDARY__REQUEST__PASSWORD_MAX_CHARS=256
RECALLUM__BOUNDARY__RATE__LOGIN_IP_ATTEMPTS=30
RECALLUM__BOUNDARY__RATE__LOGIN_IP_WINDOW_SECONDS=300
RECALLUM__BOUNDARY__RATE__LOGIN_ACCOUNT_ATTEMPTS=5
RECALLUM__BOUNDARY__RATE__LOGIN_ACCOUNT_WINDOW_SECONDS=300
RECALLUM__BOUNDARY__RATE__INVALID_MCP_AUTH_ATTEMPTS=60
RECALLUM__BOUNDARY__RATE__INVALID_MCP_AUTH_WINDOW_SECONDS=60
RECALLUM__BOUNDARY__RATE__MAX_BUCKETS=10000
```

`10.0.1.0/24` is the live `dokploy-network` overlay (Traefik is the trusted
peer). Re-inspect that network after a Dokploy upgrade before changing it.
`RECALLUM__RUNTIME__WORKERS` and `RECALLUM__WEB__ALLOWED_ORIGIN` currently
default to the same values; set them explicitly so a future image default
cannot silently diverge.

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
query behind. `--trigram-weight` / `--importance-weight` / `--usage-weight`
override one knob for an A/B run; numbers are only comparable against the
same dataset and the same embedding model. Persist a winning value via the
`RECALLUM__LIMITS__*` environment variables.

This ranking evaluation is deliberately separate from the workflow/checkpoint
evaluator (`scripts/eval_agent_workflow.py`): that one measures how well agents
follow an adherence policy across recorded runs, while `recallum-admin eval`
measures retrieval ranking quality on the golden dataset. The two are never
blended — this report carries only MRR, recall@k and the tagged misses list.

### Comparing the usage vote

`recall_usage_weight` (the vote `recall_count` gets in fusion) ships at `0.0`
so it never affects production ranking until a measured decision raises it.
To compare a candidate weight against the baseline on the *identical* dataset
and configuration, run the same command twice and diff the reports:

```bash
docker compose exec recallum uv run --no-sync recallum-admin eval \
  --email eval@example.com --dataset scripts/eval_dataset.json                # baseline: usage weight 0.0
docker compose exec recallum uv run --no-sync recallum-admin eval \
  --email eval@example.com --dataset scripts/eval_dataset.json --usage-weight 0.3  # candidate
```

The applied override is recorded in the report's `tunables:` line. Note that
the eval user's memories start with `recall_count = 0`; run the baseline first
so its ordinary recalls accumulate usage, then read the candidate report for
what a positive weight actually changes.

**Measured decision (2026-08-22, `embeddinggemma:300m`, dataset with 18
corpus rows / 28 queries, k=10):** the default stays at `0.0`. After a seeding
pass accumulated organic usage, weights 0.1 / 0.3 / 0.5 / 1.0 degraded overall
MRR monotonically (0.82 baseline → 0.80 → 0.79 → 0.78 → 0.75) and at 1.0 also
lost recall@10 (1.00 → 0.96, first hard miss). The damage concentrated in the
weakest tags (`es-en` MRR 0.49 → 0.19): high-usage rows displace correct but
weakly-matched candidates — exactly the rich-get-richer failure the cap was
designed to contain. Do not raise `RECALLUM__LIMITS__RECALL_USAGE_WEIGHT`
above 0 unless a future dataset revision (with usage patterns that correlate
with relevance rather than with prior rankings) reverses this result.

`reconfirm_count` (stamped by `reconfirm`, and by `remember`'s exact-dedup
and race paths) accumulates independently of the serve counts above: it is
an agent explicitly verifying a memory against reality, not a passive serve,
so it is not implicated by the measured decision against `recall_count`. It
is the candidate cleaner utility signal for any future ranking experiment —
a weight for it would go through the same measured-activation contract
(ships at `0.0`, raised only after a comparison run like the ones above). No
ranking change now.

### Comparing the freshness vote

`recall_freshness_weight` (the vote `reconfirmed_at`, or `created_at` when a
memory was never reconfirmed, gets in fusion) ships at `0.0` for the same
reason as the usage vote: it must not affect production ranking until a
measured decision raises it. Compare a candidate weight against the baseline
the same way, on the identical dataset and configuration:

```bash
docker compose exec recallum uv run --no-sync recallum-admin eval \
  --email eval@example.com --dataset scripts/eval_dataset.json                     # baseline: freshness weight 0.0
docker compose exec recallum uv run --no-sync recallum-admin eval \
  --email eval@example.com --dataset scripts/eval_dataset.json --freshness-weight 0.3  # candidate
```

The applied override is recorded in the report's `tunables:` line, same as
the usage vote.

**Known limitation:** the current golden dataset seeds its entire corpus in
one pass, so every row's `reconfirmed_at`/`created_at` lands within the same
narrow window — freshness has almost nothing to discriminate on in this
dataset, and a candidate-weight run against it will look like a no-op
regardless of whether the vote is doing anything useful. A measured
activation decision needs a dataset revision with time-spread fixtures
(seeded across days or weeks, with a subset explicitly reconfirmed later)
before its numbers mean anything. Until that revision exists, the default
stays at `0.0`.

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

## Corpus hygiene report

`recallum-admin hygiene` is a read-only report over one user's active
memories: it never mutates, merges, or forgets anything. Write-time `similar`
warnings from `remember` are advisory — an agent that ignores one leaves a
near-duplicate active forever, and nothing else revisits it. This closes that
loop from the outside by reusing the same bounded semantic-pair projection
`memory_graph` renders, then reporting two things:

- **Merge candidates (same-bucket):** clusters of >=2 active memories in one
  scope+project bucket, mutually linked by pairwise similarity at or above the
  threshold. A merge is only ever valid within one bucket, so clusters never
  cross scope or project even when the underlying pairs would otherwise chain
  across one.
- **Contradiction candidates:** pairs (within the same bucket) where a
  negation/reversal cue — English or Spanish (`not`, `no longer`, `never`,
  `instead of`, `deprecated`, `ya no`, `en lugar de`, `nunca`, `obsoleto`) —
  appears in one memory's content but not the other's. This is a heuristic for
  human or agent review, not a verdict; act on it with `update`,
  `merge_memories`, or `forget`.

```bash
docker compose exec recallum uv run --no-sync recallum-admin hygiene \
  --email user@example.com
```

`--min-similarity` overrides the floor (default: `similar_min_similarity`,
0.85); `--limit` caps how many active memories one run scans (default 500,
matching the quadratic cost of the underlying pairwise comparison). When the
cap trims the corpus, the report says so explicitly instead of truncating
silently — rerun with a higher `--limit` for a complete sweep of a larger
corpus.

## Project-memory bootstrap

`recallum-admin bootstrap` cheaply seeds candidate memories from a fixed,
bounded allowlist of well-known project files -- README, AGENTS.md,
CLAUDE.md, pyproject.toml, package.json, Dockerfile, docker-compose.yml, plus
the mere presence of `src/`, `tests/`, `docs/`, `migrations/` -- instead of
walking the whole repository or requiring an LLM. Parsing is deterministic
(`tomllib`/`json` plus a couple of markdown heuristics), and candidates are
capped at 10, preferring structured files (pyproject.toml, package.json) over
prose. It never dumps a whole file into a candidate.

```bash
docker compose exec recallum uv run --no-sync recallum-admin bootstrap \
  --email user@example.com --project my-project --path /path/to/repo
```

Dry-run is the default: candidates are printed for review, and nothing is
stored. Add `--apply` to persist them through the same `remember_batch` path
an agent uses, which gives exact-content dedup, the similar advisory and user
isolation for free -- re-running bootstrap over unchanged files is safe and
creates no duplicates. When the cap trims the candidate list, the report says
so explicitly instead of truncating silently.

## Working memory (TTL)

`remember`, `remember_batch` items, and `update` accept an optional
`ttl_seconds` (positive, capped at `ttl_max_seconds`, default 365 days) that
stores `expires_at = now() + ttl_seconds`. `update` also accepts
`clear_expiry: true` to revert a memory to durable (no expiry). No memory
expires by default -- `expires_at` is NULL unless a TTL was declared.

Once past its expiry, a memory is excluded from every read surface (`recall`,
`context`, `list_memories`, `get_memory`, the `similar` advisory,
`related_memories`, `memory_graph`) without any background job -- the check
is a lazy, read-time predicate, same shape as the existing soft-delete
filter. The row is retained, never physically deleted, and an expired
duplicate never blocks re-remembering the same content: a repeat comes back
as a fresh row rather than reviving the stale one. Use TTL for short-lived
facts ("branch X is blocked this week"); omit it for durable context.

## Graph edge strategy (scalable path)

`memory_graph` computes edges with a pairwise O(n²) self-join by default, which
is correct but quadratic in the number of active nodes. A scalable path is
available: a bounded per-node kNN query over the already-selected node subset,
using the existing embedding index (no new index is required).

Activate the scalable path when **either** of these holds:

- The operator flag `RECALLUM__LIMITS__GRAPH_SCALABLE_ENABLED=true` is set.
- The active node count is **strictly above**
  `RECALLUM__LIMITS__GRAPH_SCALABLE_MIN_NODES` (default `500`), with the flag
  off or unset.

Default deployments auto-route above 500 active memories: the flag ships
unset and the default threshold (500) sits below the default node ceiling
(1000), so the bounded per-node kNN path replaces the O(n²) self-join before
a large user's projection would otherwise become expensive. Routing compares
the **uncapped** active node count against the threshold, not the number of
presented nodes, so a user with more than 500 active memories auto-routes to
the scalable path even with the flag off. Raise `graph_scalable_min_nodes`
above your expected active-memory volume if the scalable path must only ever
be an explicit opt-in.

On the scalable path, each node contributes at most `graph_max_neighbours`
edges; edges still require `graph_min_similarity` and matching embedding
models. Truncation stays honest and observable: the response's `edge_total`
reports the number of qualifying undirected pairs before the per-node cap, and
`edges_truncated` is true when at least one qualifying pair was dropped because
an endpoint reached the cap. The per-node kNN keeps the returned edge rows
bounded; computing the exact pre-cap `edge_total` still evaluates the
qualifying pairs themselves, so the exact count shares the cost of the
pairwise path even though the edges themselves stay bounded. `total`/`truncated`
keep their existing node-level meaning. To see both paths produce the same
edges and signals before enabling the flag, run the graph parity/truncation
integration tests (`tests/integration/test_graph_edges.py`).

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

For a version that includes `0020_invalidate_memory_profiles`:

1. Stop every new Recallum process (remove the Traefik route or disable the
   router label so traffic cannot hit a mixed pair).
2. Downgrade `0020` (`alembic downgrade 0019_memory_code_anchors`). That
   **re-invalidates** `memory_profiles` (`generation=-1` again); it does not
   restore previous static contents. Source memories and skills stay intact.
   The previous static policy returns on rebuild after the old version starts.
3. Start the previous Recallum image tag.

Volumes are preserved. Do not treat this as a schema-only additive rollback:
skipping the `0020` downgrade leaves profiles that a new process already
rebuilt under the new rule.

### MCP unexpected errors

Unexpected tool and profile-resource failures return
`internal server error (reference: mcp-<32 lowercase hex>)`. The same
`mcp-` + 32-hex value is the sanitized log `correlation` / `correlation_id`
field (`MCP operation failure class=... correlation=mcp-...`). Grep existing
operator logs for that reference; there is no public lookup header, store, or
endpoint. HTTP `X-Request-ID` stays a separate contract.

Do **not** blindly retry a mutation whose result is uncertain after an
unexpected error — the write may have committed before the failure. Inspect
the correlated log, then verify state (`get_memory` / `list_memories`) before
repeating the call.

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
