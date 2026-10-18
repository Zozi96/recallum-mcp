# Design

## Context

Ver `proposal.md` para la motivación y los conteos de statements por llamada. El estado actual que condiciona el diseño:

- Un solo worker Granian (MCP stateful) y un pool asyncpg de 5+5 compartido entre foreground, telemetría y reconstrucción de perfiles. Cada transacción de usuario paga `set_config('app.current_user_id')` por RLS: ese costo es estructural y no se toca.
- La búsqueda híbrida ya corre en una sola transacción (`search_candidates` / `context_snapshot`) y `_light()` ya evita traer `embedding`/`content_tsv`. Lo que queda es reducir statements dentro y alrededor de esa transacción.
- Ya existen dos patrones de worker acotado con lifecycle propio (`TelemetryBuffer`, `ProfileRebuildQueue`): cualquier diferimiento nuevo reusa ese molde en vez de inventar otro.
- Los requisitos vigentes acotan el diseño: snapshot único de `context`, «recall no invalida el perfil», «dynamic fresco tras recall», registro de telemetría sin escritura sincrónica por llamada, y prohibición de elegir tunables de retrieval sin el evaluador versionado.

## Goals / Non-Goals

**Goals:**

- Bajar statements y transacciones por llamada en `recall`, `context`, `remember`, `remember_batch`, `related_memories` y `match_skills`, con presupuestos verificables por test.
- Que ninguna lectura espere una escritura de señal (uso) ni un timeout de escritura de Ollama.
- Que cada lote sea reversible por separado y quede fuera si la fase 0 no lo justifica.

**Non-Goals:**

- Cambiar pesos de fusión, pisos de similitud o semántica de ranking (sólo se valida que no cambien).
- Particionar el índice HNSW por tenant, subir el pool «por las dudas» o pasar a MCP stateless/multi-worker.
- Cachear resultados de `recall`/`context` completos: la frescura del perfil y del corpus manda sobre ese ahorro.

## Decisions

### D0. La fase 0 produce números que podan lotes, no un informe decorativo

Antes de cualquier lote: p50/p95 por herramienta desde `tool_activity` (la duración por llamada ya se persiste), `EXPLAIN (ANALYZE, BUFFERS)` de las tres piernas de búsqueda, `related_to`, la selección dynamic y los tops de `context`, y conteo de statements por llamada. El resultado se anota en `tasks.md` al ejecutar y cada lote declara su comparación antes/después. Si una pierna ya es despreciable a la escala real, su lote se cierra como «no justificado» con la evidencia adjunta. Alternativa descartada: benchmark sintético nuevo end-to-end — el dataset de ranking versionado y `tool_activity` ya dan calidad y latencia real sin construir infraestructura.

### D1. `ef_search` explícito junto a `iterative_scan`

pgvector usa `hnsw.ef_search=40` por defecto y las piernas piden hasta 60 candidatos con filtros post-escaneo (usuario, visibilidad, modelo). Se fija `ef_search` en un valor con margen sobre el tope de candidatos (100 propuesto) en el mismo punto donde hoy se fija `iterative_scan`. Como `strict_order` ya garantiza orden exacto reescaneando, subir `ef_search` sólo reduce pasadas: el conjunto servido no puede empeorar, pero igual se corre el evaluador de ranking antes/después como exige la spec. Alternativa descartada: calcular `ef_search` por llamada según `limit` — el filtrado multi-tenant hace que el margen necesario no dependa del `limit` pedido.

### D2. `related_memories` en dos pasos indexables; el grafo, sólo si el plan mejora

Hoy `related_to` ordena por `1 - distancia` entre dos columnas: pgvector no puede usar HNSW ahí. Se reescribe dentro de la misma transacción RLS: (1) leer `embedding` y `embedding_model` de la semilla activa propia (ausente/ajena ⇒ lista vacía, igual que hoy), (2) vecinos con `ORDER BY embedding <=> :semilla` y el mismo piso de similitud y la misma regla de modelo comparable. Para el LATERAL de `_scalable_graph_edges` se cambia el orden a distancia ascendente y se conserva sólo si `EXPLAIN` muestra uso del índice o mejora clara; si el parámetro correlacionado sigue sin indexarse, se revierte ese punto y queda documentado.

### D3. Anclas sólo para lo servido

`Memory.anchors` con `lazy="selectin"` dispara una consulta por cada SELECT de memorias, incluidos los pools de candidatos que en su mayoría se descartan. Los pools de búsqueda (`search_candidates`, focos y tops de `context_snapshot`, `similar_active`) pasan a cargar con `noload` de anclas, y el servicio adjunta las anclas de los ítems finalmente servidos con una única consulta por llamada (`memory_id IN (...)`). `get_memory`, `list_memories` e historial conservan `selectin` porque devuelven todo lo que traen. Alternativa descartada: bajar `MAX_CANDIDATES` — cambia la calidad de fusión para ahorrar lo que esta decisión ahorra sin tocarla.

### D4. Registro de uso diferido con lectura de lo propio para dynamic

Nuevo buffer en memoria con el molde de `TelemetryBuffer` (acotado, un worker con lifecycle, volcado por tamaño o intervalo, volcado final en cierre ordenado, contadores de descarte/fallo). Acumula por `(user_id, memory_id)` los incrementos de `recall_count`/`context_count` y el último `last_recalled_at` servido; el volcado aplica un único `UPDATE ... FROM unnest(...)` por usuario y lote dentro de su sesión RLS. `recall` y `context` sólo encolan: cero espera de DB, cumpliendo el nuevo requisito de `agent-memory-retrieval` y la letra ya vigente de «Snapshot único de context».

Para que «dynamic fresco tras recall» siga siendo cierto, `context` y la lectura de perfil vuelcan primero lo pendiente **de ese usuario** si lo hay (a lo sumo una transacción que `context` ya pagaba hoy en forma de `mark_seen_in_context`), y recién entonces leen el snapshot. Alternativa descartada: fusionar lo pendiente en Python durante la selección dynamic — la selección es SQL con orden y límite; fusionar en memoria obligaría a replicarla. Los contadores expuestos por `get_memory`/`list_memories` pueden rezagarse hasta la ventana: es exactamente lo que el requisito modificado declara. Registrar uso sigue sin incrementar `memory_generation`.

### D5. Knobs HNSW a `server_settings`; el threshold de trigram se queda

`hnsw.iterative_scan` y `hnsw.ef_search` son constantes por proceso: pasan a `_database_connect_args` junto al `statement_timeout` existente y desaparecen los `SET LOCAL` por búsqueda en ambos repositorios. El threshold de trigram, en cambio, llega hoy como parámetro desde `MemoryLimits` vía el servicio; moverlo a la conexión duplicaría su fuente de verdad, así que conserva su `set_config` transaccional (un solo statement y sólo cuando la pierna corre). Se agrega un test de integración que verifica los valores efectivos sobre una conexión del pool. Si en la fase de implementación aparece un camino de engine que no pase por el container, ese camino conserva el `SET LOCAL` en vez de forzar la unificación.

### D6. Dedup antes de embeber, con reverificación dentro de la escritura

`remember` hace un pre-chequeo de hash en una transacción corta de lectura y sólo embebe si no hay duplicado activo; `_remember_in_session` reverifica dentro de la transacción de escritura como hoy, así que la condición de carrera sigue resuelta por el índice único y el reintento existente. `remember_batch` resuelve todos los hashes en una sola consulta y embebe sólo los faltantes. Costo aceptado: una transacción corta extra en el camino sin duplicado, órdenes de magnitud menor que un embedding. Alternativa descartada: mover el embedding adentro de la sesión tras el chequeo — retendría una conexión del pool durante el HTTP a Ollama, justo lo que el código actual evita a propósito.

### D7. Presupuesto de lectura para embeddings: timeout corto, ventana negativa y cache de consultas

El cliente de embeddings distingue lectura de escritura: las lecturas (`recall`, foco de `context`, `match_skills`) usan un timeout propio corto (default propuesto 3s, configurable) y, tras un fallo, una ventana breve (default propuesto 5s) en la que degradan sin reintentar; las escrituras conservan el timeout completo y siempre intentan, porque un vector marcador es deuda persistente y una lectura degradada no. Sobre el camino de lectura se agrega una cache LRU acotada por `(modelo, texto normalizado)` — los vectores son inmutables por modelo y los agentes repiten `context` con el mismo foco. La degradación por ventana cuenta como degradada en telemetría igual que la degradación por fallo, como declara el requisito modificado.

### D8. Auth: una transacción para lookup + touch, y TTL decidido por hit rate

El repositorio de API keys resuelve hash y refresco de `last_used_at` en una misma sesión admin cuando el refresco corresponde. `TokenAuthenticator` suma contadores de aciertos/fallos expuestos en la superficie de métricas (requisito nuevo de `agent-usage-telemetry`). Con el hit rate de la fase 0 se decide el default: si a 5s el acierto es marginal (la cadencia entre llamadas MCP la marca el LLM, no el agente en ráfaga), el default sube a 30s actualizando el comentario que declara el TTL como demora máxima de revocación. La spec de `mcp-agent-integration` ya contempla esa ventana opt-in: no requiere delta.

### D9. Lote de escalado acotado y medible

- **Índice dynamic**: migración con índice parcial `(user_id, last_recalled_at DESC) WHERE deleted_at IS NULL AND last_recalled_at IS NOT NULL`, reflejado en `models.py` como los demás btree. Sirve a `context_snapshot` y a `list_active_for_profile`.
- **Tops proporcionales**: la ventana pool-wide cap+1 se implementó y se revirtió porque podía desviarse de los tops sin cota: `assemble` empaqueta por categoría en orden de estrategia, así que cuando una categoría desborda la ventana deja fuera una categoría temprana de empaquetado. Cada pool pide ahora `ROW_NUMBER() OVER (PARTITION BY category ORDER BY importance DESC, created_at DESC, id)` con límite `effective_max_items + min(effective_max_items, profile_context_max_items) + 1` (una sentencia por pool); la ventana por categoría preserva los groups, omitted y omitted_by_category de los tops sin cota a cualquier presupuesto y elimina esa desviación.
- **Rebuild en una transacción**: generación, candidatos y upsert con CAS comparten una sesión por intento (hoy son tres). No se toca la generación por usuario ni el abanico de claves tras un guardado global: es correcto que una memoria global afecte a todos los perfiles de proyecto, y la cola ya coalesce ráfagas; lo que se abarata es cada reconstrucción.
- **Consultas colapsadas**: `statistics()` pasa de nueve consultas a dos (agregados con `FILTER`/agrupaciones y la serie por día), e `history()` a una CTE recursiva con guarda de ciclo, conservando formas de salida y orden.
- El conteo por categoría de cada `context` **no** se cachea por generación: la expiración por tiempo cambia el conjunto activo sin incrementar generación y un total obsoleto mentiría en `omitted`. Si la fase 0 lo muestra caliente, se revisa con el índice de esta misma decisión antes que con un cache.

### D10. Presupuestos de statements como tests de regresión

Un test de integración con listener de statements sobre el engine afirma techos por llamada para `recall` y `context` (sin foco, con foco y tras `recall`). Los techos se fijan con los números reales post-implementación, no con aspiraciones: su función es que D3/D4/D5 no se erosionen en silencio, igual que `_light()` protege hoy contra traer el vector. Alternativa descartada: afirmar latencias en tests — flaky por entorno; los statements son deterministas.

## Risks / Trade-offs

- [Subir `ef_search` encarece cada escaneo si el corpus crece mucho] → Se valida con `EXPLAIN ANALYZE` sobre el corpus real y queda como setting ajustable; `iterative_scan` sigue acotando el trabajo total.
- [El volcado-al-leer de D4 mueve el costo a `context` cuando el flujo alterna `recall`→`context`] → Aun así es una única escritura agrupada en vez de una por lectura, y `recall` (la llamada frecuente en checkpoints) queda sin escritura; la fase 0 mide la cadencia real antes de construirlo.
- [Pérdida de señal de uso ante terminación abrupta] → Acotada a la ventana, observable en métricas y sin efecto sobre memorias ni sobre el voto de uso (default 0.0); es el mismo compromiso ya aceptado para la telemetría.
- [Los knobs en `server_settings` aplican también a sesiones CLI/admin del mismo container] → Son los mismos valores que hoy se fijan por búsqueda; el test de D5 lo verifica, y cualquier camino que necesite otro valor puede seguir usando `SET LOCAL`.
- [La ventana negativa degrada lecturas unos segundos tras la recuperación de Ollama] → Ventana corta y configurable; la alternativa (esperar el timeout completo en cada lectura mientras Ollama flaquea) es estrictamente peor.
- [El default de TTL de identidad más alto amplía la ventana de revocación] → Sólo se sube si el hit rate medido lo justifica, queda declarado en config como demora máxima de revocación y el operador puede volver a 5s o a 0 sin despliegue de código.
- [Varias mejoras pueden no mover el p95 a la escala personal actual] → Es un resultado válido de la fase 0: esos lotes se podan con evidencia en vez de implementarse por inercia.

## Migration Plan

1. Fase 0 de medición (sin cambios de comportamiento; sólo contadores de métricas aditivos si hacen falta para medir).
2. Lotes en orden de `tasks.md`, cada uno con su medición antes/después y reversible por sí solo: primero knobs e índices de lectura, luego consultas por llamada, después el registro diferido (el único con cambio de requisito) y al final el lote de escalado.
3. La única migración de esquema es el índice parcial de D9 (con downgrade que lo elimina); no hay migración de datos.
4. Rollback por lote: revertir el commit del lote; los settings nuevos tienen defaults conservadores y los contadores de métricas son campos aditivos.
5. Al cerrar, correr la suite afectada, los tests de integración contra Postgres+pgvector y el evaluador de ranking comparando contra la línea de base de la fase 0.

## Open Questions

- Valor final de `ef_search` y de los timeouts/ventana de lectura: se fijan con los `EXPLAIN` y percentiles de la fase 0 dentro de los defaults propuestos; no cambian specs ni el desglose de tareas.
- Default final del TTL de identidad: acotado por D8 a «5s si el hit rate ya es alto, 30s si es marginal» y decidido con el dato medido.
