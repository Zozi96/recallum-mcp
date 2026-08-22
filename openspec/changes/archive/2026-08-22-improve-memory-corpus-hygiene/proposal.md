## Why

Los agentes escriben más rápido de lo que el corpus se limpia. Ya existen `similar`, cola stale, `reconfirm`, `update` y `merge_memories`, pero la guía de higiene es fácil de saltar: duplicados semánticos, contradicciones sin resolver y hechos stale degradan recall y contexto sin fallar el sistema.

## What Changes

- Endurecer la guía accionable de `stale-review` y de la skill/hooks para que cada ítem stale tenga un desenlace explícito (`reconfirm` / `update` / `forget` / `merge_memories`).
- Hacer explícito el criterio merge-vs-update ante `similar` (reexpresión → merge; contradicción → update del incorrecto; nunca auto-resolver).
- Opcionalmente mejorar la superficie self-service/web para revisar cola stale y vecinos sin exponer embeddings.
- No cambiar umbrales de similitud por defecto, no auto-merge, no auto-forget, no ranking ni API de escritura nueva salvo lo necesario para higiene guiada.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-lifecycle`: Criterio normativo de reconciliación ante similares y cola stale (sin resolución automática de contradicciones).
- `mcp-agent-integration`: Prompts `stale-review` y `capture-scan` MUST orientar desenlaces explícitos y merge-vs-update.
- `agent-session-bootstrap`: La guía de vecinos/reconfirmación/cola obsoleta MUST reflejar el mismo criterio de higiene.
- `web-self-service-api`: Superficie de lectura/acción acotada para cola stale y vecinos cuando exista UI self-service (sin exponer vectores).

## Impact

- Afecta prompts MCP, skill/hooks del plugin, posiblemente endpoints self-service y UI asociada.
- No altera dedup exacta, RLS, ranking ni el contrato de no auto-resolver contradicciones.
