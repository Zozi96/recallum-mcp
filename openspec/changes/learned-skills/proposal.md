## Why

A memory says “this is how we solved it.” A skill says “when this happens, follow this procedure.” Agents currently stuff procedures into `fact` memories, which pollutes retrieval and cannot version steps, triggers, or constraints. We need a small Skill entity — not a marketplace, not auto-extracted conversation sludge.

## What Changes

- Introduce a `skills` store owned by the same user, with GLOBAL/PROJECT scope (same visibility rules as memories; no AGENT scope in this change).
- Fields: `name`, `description`, `triggers`, `steps`, `constraints`, `version`, `project`, `source_type`/`source_ref` if provenance has landed, embedding + FTS like memories.
- MCP: add `save_skill`, `match_skills`, `get_skill`, `forget_skill`. No marketplace, no sharing between users.
- Writes are agent-driven (same as `remember`). Automatic extraction from sessions is **out of scope** (P2, and only after capture quality is proven).
- Garbage control: unique `(user, scope, project, name)` among active skills; similar advisory on save; exact content-hash dedup of `steps`.
- **BREAKING** for the MCP tool-count contract: `mcp-agent-integration` today requires exactly eleven tools.

## Capabilities

### New Capabilities

- `learned-skills`: almacenamiento, matching y ciclo de vida de procedimientos versionados, distintos de memorias atómicas.

### Modified Capabilities

- `mcp-agent-integration`: el conjunto de tools deja de ser exactamente once; se anuncian las cuatro tools de skill. El grafo temático sigue sin publicarse por MCP.

## Impact

- Nueva tabla `skills` (pgvector + tsvector), repositorio, servicio, tools MCP, skill del plugin (cuándo skill vs memory).
- Reutiliza embeddings Ollama, FTS inglés, RLS, visibilidad global/proyecto.
- No Taskiq, no LLM proxy, no extracción automática, no AGENT scope.
