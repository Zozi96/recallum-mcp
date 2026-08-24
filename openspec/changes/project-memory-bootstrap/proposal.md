## Why

New projects start empty: agents re-discover runtime, conventions, and layout every session. Tencent-style whole-repo LLM ingestion is too expensive and too wrong. Recallum should cheaply extract a handful of candidate atoms from well-known files and let the agent confirm them with existing `remember_batch`.

## What Changes

- Add `recallum-admin bootstrap --email --project --path` that scans a bounded allowlist (README, AGENTS.md, CLAUDE.md, pyproject.toml, package.json, docker-compose.yml, Dockerfile, presence of `src/`, `tests/`, `docs/`, `migrations/`) and prints candidate memories (runtime, frameworks, test command, conventions found as headings).
- Extraction is deterministic (parsers + heuristics). An LLM MAY optionally rewrite candidates into English atoms, but bootstrap MUST succeed without any LLM.
- Candidates are **not** auto-written. The CLI prints them; an agent or operator submits via `remember_batch` (or a later thin MCP wrapper).
- No recursive source-code walk, no “understand the whole repo,” no conversation import.
- Not **BREAKING**.

## Capabilities

### New Capabilities

- `project-memory-bootstrap`: inicialización incremental y barata de contexto de proyecto a partir de archivos conocidos.

### Modified Capabilities

Ninguna a nivel de tools MCP en este change (CLI only). Si más adelante se añade un tool MCP, será un change aparte para no romper el recuento de tools dos veces.

## Impact

- Nuevo comando en `recallum-admin`, parsers pequeños, tests de fixtures de repos.
- Reutiliza `remember` semántica (inglés, categorías, proyecto canónico) sin persistir desde el CLI salvo flag explícito `--apply` documentado y opt-in.
- No Taskiq, no CodeGraph, no embeddings obligatorios para el scan.
