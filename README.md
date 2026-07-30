# Recallum

Private, self-hosted persistent memory for AI coding agents (Codex, Claude
Code), exposed as an MCP server over Streamable HTTP. No paid APIs: embeddings
are generated locally with Ollama, storage is PostgreSQL with pgvector.

## Features

- **Eight MCP tools**: `remember`, `remember_batch`, `recall`, `context`,
  `get_memory`, `list_memories`, `update`, `forget`.
- **Explicit supersession**: `update` retires a memory and links it to its
  replacement; `remember` reports similar existing memories so contradictions
  surface where they are created, and are never resolved automatically.
- **Hybrid retrieval**: pgvector cosine similarity + PostgreSQL full-text
  ranking fused with Reciprocal Rank Fusion; graceful textual-only degradation
  when Ollama is down. The vector leg only compares same-model vectors; after
  changing the embedding model, `recallum-admin reembed` restamps stored rows.
- **Strict per-user isolation**: individual API keys (stored as SHA-256 hashes),
  explicit user filters, and Row-Level Security as a second barrier.
- **Atomic memories only**: preferences, decisions, constraints, facts — never
  full conversations. Global and per-project scopes. Exact duplicates are
  deduplicated.
- **Operational endpoints**: `/healthz` (liveness) and `/readyz` (readiness).

## Stack

FastAPI · FastMCP 3.x · Dependency Injector · SQLAlchemy 2.x (asyncpg) ·
pgvector · Alembic · Ollama (`embeddinggemma:300m-qat-q4_0`, 768 dims) ·
Python 3.14

## Quick start (local full stack)

```bash
cd deploy && docker compose up -d --build
docker compose exec ollama ollama pull embeddinggemma:300m-qat-q4_0
docker compose exec recallum uv run --no-sync recallum-admin create-user --email you@example.com
docker compose exec recallum uv run --no-sync recallum-admin issue-key --email you@example.com
```

## Development

```bash
uv sync
uv run pytest tests/unit                 # fast, no external services
uv run pytest tests/integration          # needs Docker (pgvector container)
uv run ruff check recallum tests
```

## Deployment

See [docs/operations.md](docs/operations.md) for the VPS runbook
(Dokploy/Traefik, model download, migrations, backups) and
[docs/clients.md](docs/clients.md) for wiring up Codex and Claude Code.
