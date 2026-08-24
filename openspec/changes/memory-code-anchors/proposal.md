## Why

Hybrid retrieval already matches identifiers (`PaymentService.capture`, `src/domain/users.py`) via FTS + trigram, but a memory cannot declare a structured link to a file or symbol. We want `recall(symbol="PaymentService.capture")` to return decisions, failures, and skills about that symbol — without Recallum owning a CodeGraph.

## What Changes

- Allow a memory (and a skill, if `learned-skills` has landed) to carry zero or more **code anchors**: `file`, `symbol`, or `module` plus a verbatim identifier.
- `recall` accepts optional `symbol` / `file` filters that restrict the candidate set **before** RRF (exact/normalized match on anchors, not a graph walk).
- Do **not** parse repositories, store ASTs, or compute callers/callees inside Recallum. External CodeGraph remains a separate MCP. Anchors are declared by the agent (or later by bootstrap).
- Not **BREAKING**: anchors optional; unanchored memories stay fully reachable by query text.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-lifecycle`: anclas de código opcionales en memorias.
- `agent-memory-retrieval`: filtro `symbol` / `file` previo a la fusión.
- `mcp-agent-integration`: argumentos opcionales en `remember` y `recall`.

## Impact

- Tabla `memory_anchors` (o JSONB validado si el volumen esperado es bajo — design decides the simpler option) con índices btree/trigram on identifier.
- `MemoryService.remember` / `recall`, tests de identificadores.
- No nuevo motor de grafo; el grafo temático de memorias permanece independiente.
