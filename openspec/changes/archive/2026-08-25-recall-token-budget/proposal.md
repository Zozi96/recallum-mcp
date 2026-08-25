## Why

`recall` still stops only at `top_k` / `limit`, and `context` budgets items and characters, not tokens. Coding agents need the smallest correct snapshot for a task type (debug, review, planning), not a larger pile of important-but-wrong-category memories.

## What Changes

- Pack `recall` (and optionally `context`) against an estimated token budget in addition to the existing item cap.
- Add an optional `strategy` (`coding`, `debugging`, `planning`, `review`, `architecture`) that only reorders already-retrieved candidates by category priority inside the budget. It does not add a new retrieval engine, reranker, or LLM call.
- Keep hybrid retrieval (pgvector + PostgreSQL FTS + trigram + RRF) unchanged.
- Default strategy remains today's behaviour: importance + retrieval fusion, category presentation order for `context` unchanged unless `strategy` is set.
- Not **BREAKING**: new optional arguments; omitted `max_tokens` / `strategy` preserve current packing.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-retrieval`: presupuesto de tokens además de ítems/caracteres; estrategia de empaquetado por tipo de tarea.
- `mcp-agent-integration`: `recall` y `context` aceptan `max_tokens` y `strategy` opcionales.

## Impact

- `MemoryService.recall` / `context`, `SessionContextBudget`, `MemoryLimits`, esquemas MCP y self-service.
- Tests de presupuesto (`test_context_budget.py`, `test_service.py`) y contrato de tools.
- No toca embeddings, índices, RLS, ni añade Elasticsearch/BM25 externo.
