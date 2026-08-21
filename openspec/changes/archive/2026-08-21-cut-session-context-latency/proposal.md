## Why

`context` es el arranque de sesión y hoy paga un préstamo de latencia: cada `recall` incrementa `memory_generation` para invalidar el slice dinámico del perfil, así que el siguiente `context` reconstruye el perfil aunque el corpus no haya cambiado, y además abre 6–10 transacciones secuenciales (perfil, generation, tops, foco, count, uso). El agente siente ese costo en el primer tool call, no en el `recall` que lo provocó.

## What Changes

- Tratar `context` como **una operación de lectura de dominio**: perfil (static materializado + dynamic en vivo), pools de importancia, candidatos de foco y `total_available` observan **un solo snapshot** de base de datos bajo el mismo RLS.
- `memory_generation` sube sólo con mutaciones que cambian el corpus o la elegibilidad **estática** (create, reconfirm, update/supersede, merge, forget, reassign). Registrar `recall_count` / `last_recalled_at` MUST NOT invalidar el perfil materializado.
- El slice **dynamic** del perfil se selecciona en la lectura de `context` (y GET de perfil) a partir de `last_recalled_at` vivo, con las mismas reglas de ventana y presupuesto que hoy, sin exigir un rebuild por generation.
- El slice **static** sigue materializado y versionado por generation; rebuild eager tras mutaciones y lazy si la fila falta o su generation no coincide.
- `mark_seen_in_context` / `mark_recalled` siguen fail-open y **fuera** de la transacción de lectura (no alargan el snapshot ni ensucian generation).
- Sin **BREAKING** de contratos MCP/HTTP: misma forma de `context`, mismos campos de perfil, mismos contadores de uso. Cambia frescura del static (ya no se reconstruye por recall) y el costo del bootstrap.
- Fuera de este change: batch de embeddings / `remember_batch` interno, caché de query embeddings, knobs de ops (`OLLAMA_KEEP_ALIVE`, `identity_cache_seconds`), índice GIN parcial de `content_tsv`, grafo kNN, ranking, workers > 1.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `memory-profile`: Generation deja de significar “cualquier cosa que el perfil lee”. Static permanece generation-keyed; dynamic se arma en lectura; recall no fuerza rebuild.
- `agent-memory-retrieval`: `context` observa un snapshot único para perfil, importancia, foco y conteo; el registro de uso no forma parte de esa transacción ni invalida el perfil.

## Impact

- **Server**: `MemoryService.context` / `_ensure_profile` / `rebuild_profile`; `MemoryRepository` (nuevo método de snapshot o equivalente, `mark_recalled` sin `_increment_generation`); selección de profile (`profile_select`) para static persistido vs dynamic live.
- **MCP / HTTP**: sin cambios de schema; `context`, recurso de perfil y GET self-service deben seguir sirviendo static+dynamic coherentes.
- **Plugin**: sin cambio de skill/hook; el digest de sesión se beneficia de un `context` más barato.
- **Tests**: contratos de generation, rebuild lazy, y que un recall no dispara rebuild; `context` con foco sigue degradando si embeddings fallan.
- **Ops**: ningún knob nuevo; el statement_timeout de 1s sigue acotando la transacción única.
