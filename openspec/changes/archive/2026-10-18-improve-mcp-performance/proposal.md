# Proposal

## Why

Cada llamada MCP paga más round trips de los necesarios: un `recall` ejecuta ~12 statements en 2 transacciones más 1 HTTP a Ollama, y un `context` con foco ~19, sobre un pool de 5 conexiones compartido con la telemetría y la reconstrucción de perfiles. Un audit estático del código encontró ocho ineficiencias concretas (HNSW sub-configurado, consultas que no pueden usar el índice vectorial, carga ansiosa de anclas, escrituras sincrónicas dentro de lecturas, embeddings calculados para duplicados, timeouts de degradación de 30s, un cache de identidad desalineado con la cadencia real MCP y `SET LOCAL` repetidos por transacción) más cuatro riesgos de escalado. Este cambio los ataca todos, pero midiendo primero: cada mejora entra sólo si la línea de base de la fase 0 la justifica y la medición posterior la confirma.

## What Changes

- **Fase 0 — línea de base obligatoria.** Antes de tocar código: percentiles de latencia por herramienta desde `tool_activity`, `EXPLAIN (ANALYZE, BUFFERS)` de las consultas calientes y conteo de statements por llamada; la superficie de métricas expone además aciertos/fallos del cache de identidad para decidir su TTL con datos. Cada lote posterior compara contra esta base y, lo que toca retrieval, contra el evaluador de ranking versionado.
- **Recuperación vectorial.** `hnsw.ef_search` explícito y coherente con el límite de candidatos en todas las piernas vectoriales; `related_memories` reescrito para poder usar el índice HNSW (hoy ordena por `1 - distancia` entre columnas y escanea sin índice); corrección del mismo patrón de orden en el LATERAL del grafo.
- **Menos consultas por llamada.** Las anclas dejan de cargarse con `selectin` para cada candidato descartado y se cargan sólo para los resultados servidos; los knobs constantes por proceso (`hnsw.*`, threshold de trigram) dejan de repetirse como `SET LOCAL` por transacción.
- **Lecturas sin escritura sincrónica.** El registro de uso de `recall`/`context` (`recall_count`, `context_count`, `last_recalled_at`) deja de hacer `await` de una transacción de escritura antes de responder y pasa a un buffer acotado con volcado agrupado, el mismo patrón ya vigente para la telemetría de actividad. La siguiente asamblea del slice dynamic del mismo usuario MUST ver ese uso (volcado o fusión en memoria), y la pérdida ante terminación abrupta queda acotada y observable.
- **Embeddings sin desperdicio.** `remember`/`remember_batch` chequean duplicados exactos por hash antes de embeber; las lecturas degradan a textual dentro de un presupuesto temporal acotado (timeout de lectura corto y ventana negativa breve tras un fallo) en vez de esperar hasta 30s por llamada; cache acotada de embeddings de consulta repetidos.
- **Autenticación medida.** El `touch` de `last_used_at` deja de costar una segunda transacción; el TTL por defecto del cache de identidad se ajusta según el hit rate medido en fase 0, dentro de la semántica de ventana de revocación ya especificada (sin cambio de requisito).
- **Escalado.** Índice parcial para la selección dynamic por `last_recalled_at`; `context` trae tops proporcionales al presupuesto pedido en vez del tope absoluto; la reconstrucción de un perfil usa una sola transacción y un guardado global deja de amplificar reconstrucciones innecesarias contra el pool compartido; `statistics()` e `history()` colapsan sus consultas secuenciales.
- Sin cambios de superficie MCP: mismas 15 herramientas, mismos esquemas de entrada/salida, sin tool arguments nuevos. Nada de esto altera ranking por intuición: todo tunable de retrieval se valida con el evaluador versionado.

## Capabilities

### New Capabilities

(ninguna: el comportamiento nuevo cabe en capabilities existentes)

### Modified Capabilities

- `agent-memory-retrieval`: el requisito de registro de uso pasa a exigir registro diferido, agrupado y acotado que MUST NOT añadir espera de base de datos a la lectura que lo origina, con visibilidad garantizada para la próxima asamblea dynamic del mismo usuario y pérdida acotada observable; la degradación textual pasa a exigir degradar dentro de un presupuesto temporal acotado por lectura, pudiendo omitir intentos de embedding durante una ventana breve tras un fallo.
- `agent-usage-telemetry`: la superficie de métricas operativas suma los contadores de aciertos/fallos del cache de identidad y los descartes/fallos del registro de uso diferido, sin contenido de usuario ni material de claves.

El resto de las mejoras (índices, `ef_search`, carga de anclas, orden de consultas, transacciones) no cambia ningún requisito observable: vive en `design.md` y `tasks.md`.

## Impact

- **Código**: `recallum/db/repositories/memory_repo.py`, `skill_repo.py`, `api_key_repo.py`; `recallum/memory/service.py`; `recallum/embeddings/ollama.py`; `recallum/auth/middleware.py`; `recallum/container.py` y `recallum/config.py` (nuevos settings acotados); `recallum/db/models.py` y una migración nueva (índice parcial); superficie de métricas en `recallum/telemetry/`.
- **Contratos preservados**: aislamiento RLS por usuario, snapshot único de `context`, «recall no invalida el perfil», dynamic fresco tras `recall`, semántica de ventana de revocación del cache de identidad, y la regla de no elegir pisos/tunables de retrieval sin el evaluador.
- **Riesgos**: a la escala personal actual varias mejoras pueden ser imperceptibles — por eso la fase 0 puede podar lotes enteros con evidencia. El registro diferido introduce pérdida acotada de una señal (nunca de memorias) ante terminación abrupta, igual que la telemetría vigente.
- **Fuera de alcance**: MCP stateless/multi-worker, particionar el HNSW por tenant, cambiar el pool por defecto sin medición, y cualquier cambio de pesos de fusión.
