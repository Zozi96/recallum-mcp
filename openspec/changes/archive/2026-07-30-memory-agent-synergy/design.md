# Design — memory-agent-synergy

## Context

Ver `proposal.md` para la motivación. Estado actual relevante:

- `context` selecciona por `importance DESC, created_at DESC` (`most_important_active`) y presupuesta
  en `SessionContextBudget.assemble`, que hoy hace `continue` sobre ítems que no caben (sesgo
  anti-largos) y sólo expone un booleano `truncated`.
- `recall` fusiona vector + texto con RRF (k=60) y un votante de importancia por ranking de
  competencia (`recall_importance_weight`, tope < 1.0).
- `remember` deduplica por sha256 del contenido normalizado por (scope, project) y reporta `similar`
  advisory filtrado hoy por scope+project+categoría.
- El modelo `Memory` no tiene señal de uso ni de reconfirmación; `importance` es estática.
- El hook del plugin (`recallum_hook.py`, compatible py3.9, sin dependencias) emite instrucciones,
  nunca datos; la clave de proyecto usa sólo `origin` o la ruta.
- Tests pinean la lista de herramientas MCP y el contrato OpenAPI del autoservicio web.

## Goals / Non-Goals

**Goals:**

- Que una sola llamada bootstrap (`context`) entregue lo genérico y lo relevante a la tarea.
- Que el agente pueda juzgar frescura y utilidad de cada memoria con campos, no con adivinanzas.
- Que los casi-duplicados entre categorías se vuelvan visibles en el momento de escribir.
- Que la captura al cierre y la delegación multi-agente tengan un camino barato y documentado.
- Fail-open en todo lo nuevo que toque la ruta de lectura o el hook.

**Non-Goals:**

- No se recalibra el ranking: el votante de uso nace con peso 0.0 (medir antes de optimizar).
- No hay decaimiento automático ni TTL de memorias.
- No hay aliasing persistente de claves de proyecto (la reasignación es una migración puntual).
- No se tocan RLS, autenticación ni el aislamiento por usuario.

## Decisions

1. **`context(focus)` como tercer pool antepuesto dentro de su categoría.** Con `focus`, el
   servicio corre la misma recuperación híbrida de `recall` (embed + `search_candidates` + RRF,
   límite propio `context_focus_limit`, default 10) y antepone los aciertos dentro de su grupo de
   categoría en orden de relevancia; el orden de categorías (preference → constraint → decision →
   fact) y el presupuesto no cambian. Si el embedding falla, la pierna enfocada degrada a textual
   (mismo contrato que `recall`). Alternativas descartadas: (a) reordenar todo el snapshot por
   relevancia al foco — enterraría constraints de importancia alta que el agente debe ver siempre;
   (b) anexar los aciertos al final de su categoría — los pools por importancia traen hasta el cap
   de ítems, así que lo anexado caía exactamente donde el presupuesto corta y el foco no se veía
   justo cuando importaba.

2. **Uso por memoria: dos columnas y un UPDATE fuera de la ruta crítica.** `recall_count int NOT
   NULL DEFAULT 0` y `last_recalled_at timestamptz NULL`. Tras armar el resultado de `recall` o
   `context`, el servicio llama `mark_recalled(user_id, ids)` (un solo UPDATE ... WHERE id IN)
   envuelto en try/except con warning: el registro jamás falla la lectura. Los valores devueltos en
   esa misma respuesta reflejan el estado previo al incremento (documentado). `list_memories` no
   cuenta como uso: es navegación diagnóstica. En RRF se añade un votante por `recall_count` con
   ranking de competencia, gobernado por `recall_usage_weight` default 0.0 — el mecanismo queda
   listo y probado, el efecto se calibra después con datos.
   Alternativa descartada: registrar en el mismo statement de lectura — acopla señal a consulta y
   complica el fail-open.

3. **`reconfirmed_at` se marca en ambas ramas de dedup.** Método de repo dedicado
   `mark_reconfirmed(user_id, memory_id)` invocado en la rama `find_active_by_hash` y en la rama de
   carrera por `IntegrityError` (una inserción concurrente del mismo contenido es una
   reconfirmación). Separado del bookkeeping de atributos para no ensuciar `update_attributes`.
   Expuesto en `MemoryOut` (y por herencia en `RecalledMemory`), `ContextItem` y `SimilarMemory`.

4. **`similar` pierde el filtro de categoría, conserva scope+project.** La categoría es una etiqueta
   de archivo que los agentes confunden; el ámbito es un espacio de nombres deliberado. Se elimina
   el parámetro `category` de `similar_active` y `_similar_to`; `SimilarMemory.category` ya existía,
   así el lector ve la discrepancia de archivo. El contrato en
   `tests/contract/memory_repository.py` se actualiza.

5. **Presupuesto transparente y truncado con marca.** `ContextResult` gana `total_available`
   (count exacto con la visibilidad combinada de la petición, un COUNT barato) y `omitted`
   (`total_available - total_items`). En `assemble`, un ítem que no cabe se recorta al presupuesto
   restante con elipsis y `content_truncated=True` si quedan al menos `context_truncate_floor`
   caracteres (default 200); si no, se corta el llenado (break) — desaparece el sesgo que rellenaba
   con ítems cortos menos importantes. La descripción de la tool indica usar `recall` cuando
   `omitted > 0`.

6. **`remember_batch` como séptima tool, no como sobrecarga de `remember`.** Ítems 1..10
   (`batch_max_items`), cada uno {content, category, project?, importance?, metadata?};
   `source_client` a nivel de lote. El servicio itera `remember` capturando por ítem
   `MemoryValidationError`/`EmbeddingError` → resultado por ítem {memory|error, created, similar}
   con éxito parcial. Lote vacío o sobre el límite: rechazo completo. Mantener `remember` intacto
   preserva la atomicidad conceptual y los esquemas simples.

7. **Reasignación de proyecto en el autoservicio web, no como tool MCP.** Mover memorias entre
   claves cambia la clave de dedup: es una migración supervisada por la persona, coherente con la
   decisión existente de que `update` no cambie scope/project. Un UPDATE con `NOT EXISTS` sobre el
   hash en destino mueve lo no colisionado; las colisiones se devuelven identificadas y no se tocan.
   Regenerar el contrato OpenAPI es parte del cambio.

8. **Digest del hook: opt-in por variables de entorno, MCP streamable-HTTP mínimo.** Sólo si
   `RECALLUM_MCP_URL` y `RECALLUM_API_KEY` están definidas (la URL no llega al entorno del hook por
   `.mcp.json`, que interpola `user_config`), el hook habla el flujo mínimo initialize →
   notifications/initialized → tools/call `context` con `urllib`, Accept JSON+SSE, propagando
   `mcp-session-id`, con presupuesto total ~2.5 s dentro del timeout de 5 s. Cualquier fallo →
   hint estándar (fail-open, sin traza al agente). El digest se pide pequeño
   (`max_items`≈10, `max_chars`≈1500) y se inyecta ya renderizado, con la nota de usar `recall`
   para profundizar. Alternativa descartada: parsear `.mcp.json` para obtener URL/token — las
   interpolaciones `${user_config.*}` no son resolubles desde el hook.

9. **Clave de proyecto: fallback a cualquier remote.** Si `origin` falta, se usa el primer remote de
   `git remote`; sólo sin remotes se cae a `local:`. Reduce fragmentación en clones que nombran
   distinto el remote.

## Risks / Trade-offs

- [El digest del hook depende de env vars que el usuario debe exportar] → documentado en la skill de
  setup; sin ellas el comportamiento actual se conserva íntegro.
- [Doble UPDATE extra por lectura (uso) y por dedup (reconfirmación)] → un statement acotado cada
  uno, fuera de la ruta de respuesta y con fail-open; sin índices nuevos porque nada filtra por esas
  columnas.
- [`remember_batch` embebe N contenidos secuencialmente] → lote acotado a 10; el coste es el mismo
  que N `remember` pero en un round-trip.
- [Quitar el filtro de categoría en `similar` puede subir el ruido del aviso] → el umbral 0.85 y el
  tope de 3 resultados ya acotan; el campo `category` en cada similar hace el ruido interpretable.
- [Reasignación parcial deja el origen dividido si hay colisiones] → respuesta explícita con ids de
  colisión; la persona resuelve (son duplicados exactos entre claves).
- [El truncado con elipsis entrega contenido incompleto] → marcado con `content_truncated` e id
  presente, recuperable vía `recall`/`list_memories`.

## Migration Plan

1. Migración Alembic `0008`: tres columnas nuevas, sin backfill (NULL/0 = "sin dato"), sin índices.
2. Deploy del servidor (cambios aditivos; clientes viejos ignoran campos nuevos).
3. Publicar plugin actualizado (hook + SKILL.md); los hooks viejos siguen funcionando contra el
   servidor nuevo.
4. Rollback: revertir imagen; la migración es inocua para el código anterior (columnas ignoradas),
   `alembic downgrade` disponible si se exige limpieza.

## Open Questions

- Valor no-cero razonable para `recall_usage_weight` — se decidirá con telemetría real; no bloquea
  specs ni tareas.
