## Why

The four categories (`preference`, `decision`, `constraint`, `fact`) are the filing system agents already use. Coding workflows also need to distinguish a failure, a solution, an architecture note, or a convention without exploding that enum or copying Tencent's RAW/FACT/CONTEXT/CORE *levels*. Level (how condensed) and kind (what it is) must stay different dimensions — and Recallum already has the level analogue in profile vs ordinary memory.

## What Changes

- Add an optional `kind` orthogonal to `category`: `failure`, `solution`, `architecture`, `convention`, `todo`, `command`.
- Keep the four categories unchanged. Do **not** add RAW/FACT/CONTEXT/CORE as storage levels or as kinds.
- `kind=todo` MUST declare a TTL (working memory); durable TODOs are out of scope (Recallum is not a task tracker).
- `recall` / `list_memories` / `context` MAY filter by `kind`.
- Strategies in `recall-token-budget` MAY use `kind` when present, falling back to `category`.
- Not **BREAKING**: `kind` is optional; existing rows are `NULL` (unspecified).

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-lifecycle`: `kind` opcional, orthogonal a `category`; TTL obligatorio para `todo`.
- `agent-memory-retrieval`: filtro opcional por `kind`.
- `mcp-agent-integration`: argumentos y respuestas de tools incluyen `kind`.

## Impact

- Check constraint / columna en `memories`, validación, esquemas MCP, skill del plugin (mapa categoría+kind).
- Independiente de provenance; puede aterrizar antes o después.
- No cambia el grafo temático ni añade categorías nuevas al enum existente.
