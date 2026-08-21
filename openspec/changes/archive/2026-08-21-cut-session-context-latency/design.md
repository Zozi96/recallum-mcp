## Context

See proposal.md (Why) and the delta specs under `memory-profile` / `agent-memory-retrieval`.

Hoy cada operación de repositorio abre su propio `SessionProvider.for_user` (pool checkout, `BEGIN`, `set_config` RLS, `COMMIT`). `context` encadena perfil, generation, rebuild opcional, dos `most_important_active`, `search_candidates` si hay foco, `count_active_visible` y `mark_seen_in_context`. `mark_recalled` incrementa `users.memory_generation`, así que el siguiente `context` toma el camino de rebuild aunque el corpus no haya cambiado.

El embed de `focus` es HTTP a Ollama (`timeout` 30s) y **no puede** vivir dentro de la transacción: el `statement_timeout` de Postgres es 1s.

## Goals / Non-Goals

**Goals:**
- Un método de repositorio que, en **una** sesión `for_user`, lea todo lo que `context` necesita del snapshot.
- Generation = mutación de corpus / elegibilidad static; `mark_recalled` deja de incrementarla.
- Static sigue en `memory_profiles`; dynamic se selecciona en lectura con las reglas actuales de `profile_select`.
- Embed de foco y registro de uso permanecen **fuera** de esa transacción.

**Non-Goals:**
- Fusionar rebuild CAS de static dentro del snapshot de lectura.
- Batch de embeddings, `remember_batch` interno, knobs de ops, índices nuevos, cambios de schema MCP/HTTP.
- Relajar RLS ni compartir sesión entre usuarios.

## Decisions

### D1 — Snapshot de lectura, no unit-of-work en el servicio

El servicio no recibe un `AsyncSession`. El repositorio expone un método de lectura (p. ej. `context_snapshot`) que abre **un** `for_user` y, en esa transacción, obtiene:

- fila de perfil + `memory_generation` (sin rebuild)
- `most_important_active` global y, si hay proyecto, de proyecto
- `search_candidates` si el caller pasó query/embedding de foco
- `count_active_visible`
- candidatos dynamic acotados (`last_recalled_at` en ventana, mismos topes)

Si la fila de perfil falta o `row.generation != generation`, el servicio hace el rebuild CAS **antes** (camino frío, igual que hoy) y después llama al snapshot. El camino caliente —generation coincidente, el de un `context` tras sólo `recall`s— es una transacción.

**Alternativa rechazada:** pasar la sesión al servicio. Rompe el aislamiento “una operación = `for_user`” y duplica RLS en dos capas.

**Alternativa rechazada:** rebuild static dentro del mismo snapshot. El CAS con `FOR UPDATE` de `users` y reintentos alargaría el tx que también corre HNSW/GIN; el statement_timeout de 1s es el techo. Rebuild sigue en su bucle de 3 intentos.

### D2 — Embed de foco antes del snapshot

```
embed(focus)?  →  [context_snapshot tx]  →  assemble  →  mark_seen (fail-open)
```

Si Ollama falla, el snapshot recibe `embedding=None` y el foco degrada a textual **dentro** del mismo tx. No se abre una segunda sesión de búsqueda.

### D3 — Generation no sube en `mark_recalled`

Quitar `_increment_generation` de `mark_recalled`. `mark_seen_in_context` ya no lo hace. Siguen subiéndola create / reconfirm / update / supersede / merge / forget / reassign.

**Alternativa rechazada:** generation “de dynamic” aparte. Dos contadores para un slice que cabe en un `SELECT` acotado en el snapshot.

**Alternativa rechazada:** seguir incrementando generation y sólo evitar el rebuild de static. El snapshot seguiría viendo mismatch y reconstruyendo static (el costo que queremos eliminar).

### D4 — Fila materializada = static; dynamic siempre live

Sin migración. En rebuild, persistir `dynamic_items=[]` y `source_memory_ids` / `content_hash` del static. Toda lectura (`context`, `get_profile`, recurso MCP, GET self-service) ensambla dynamic con `select_profile_slices` (o el helper de presupuesto dynamic) sobre candidatos del snapshot/lectura, excluyendo ids ya en static.

El `digest` **servido** se calcula en lectura sobre static + dynamic devueltos (`profile_content_hash`). `built_at` es el de la fila (última materialización static). El `content_hash` almacenado queda como integridad del static; no se expone como digest del bloque servido.

**Alternativa rechazada:** seguir persistiendo dynamic en rebuild y usarlo si generation coincide. Tras `recall` estaría obsoleto, que es el bug de frescura que el préstamo generation intentaba evitar.

**Alternativa rechazada:** drop de columna `dynamic_items`. No hace falta para cumplir el spec; se puede limpiar en un change posterior.

### D5 — Registro de uso sigue fuera

`mark_recalled` / `mark_seen_in_context` después de devolver el resultado, try/except, sin generation. ADR 0011 intacto: no unificar los dos marks.

## Risks / Trade-offs

- [statement_timeout 1s en el snapshot combinado] → Las tres patas de búsqueda **ya** corren juntas; se añaden tops + count + perfil, baratos. Si un corpus enorme rozara 1s, el fallo es el mismo techo de hoy en `search_candidates`, no uno nuevo.
- [dynamic live sin índice en `last_recalled_at`] → Corpus por usuario es pequeño y el `WHERE` va detrás de `user_id` + `deleted_at IS NULL` (índices parciales existentes). Índice extra = follow-up si un EXPLAIN lo pide.
- [digest servido ≠ hash almacenado] → Clientes que cachearan `content_hash` de la fila cruda (nadie en el plugin: usan el digest del bloque `context`) verían static-only. El contrato servido cubre ambos slices.
- [tests que asumen que `mark_recalled` ensucia generation] → Actualizar contratos/fakes; los tests de dynamic-after-recall deben seguir verdes vía ensamblado live, no vía rebuild.

## Migration Plan

1. Desplegar código. Sin Alembic.
2. Filas antiguas con `dynamic_items` poblados: las lecturas nuevas los ignoran y reescriben `[]` en el próximo rebuild por mutación.
3. Rollback = revertir el deploy. `mark_recalled` vuelve a incrementar generation; más rebuilds, comportamiento previo.

## Open Questions

Ninguna que altere specs o el desglose de tasks. El nombre exacto del DTO/método de snapshot es detalle de implementación.
