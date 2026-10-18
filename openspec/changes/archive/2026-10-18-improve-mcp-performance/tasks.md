# Tasks

## 1. Fase 0 — Línea de base de medición

- [x] 1.1 Obtener p50/p95 de duración por herramienta desde `tool_activity` con SQL y anotar la tabla resultante (herramienta, llamadas, p50, p95, % degradadas) en la descripción del PR o en una nota del cambio; verificar que cubre al menos `recall`, `context`, `remember`, `remember_batch`, `related_memories` y `match_skills`
- [x] 1.2 Capturar `EXPLAIN (ANALYZE, BUFFERS)` de las tres piernas de `search_candidates`, de `related_to`, de la selección dynamic por `last_recalled_at` y de los tops de `context` contra la base real (o una sembrada de tamaño comparable) y anotar plan y tiempo de cada una junto a la línea de base
- [x] 1.3 Contar statements y transacciones por llamada para `recall`, `context` sin foco, `context` con foco, `remember` nuevo, `remember` duplicado y `context` inmediatamente posterior a un `recall`, usando un listener de statements del engine en un script desechable o test; anotar la tabla como presupuesto inicial
- [x] 1.4 Exponer contadores de aciertos/fallos del cache de identidad en `TokenAuthenticator` y en la superficie de métricas (campos aditivos, sin material de claves), con test que verifica que el snapshot refleja aciertos y fallos tras autenticaciones repetidas y que ninguna etiqueta contiene hashes ni correos
- [x] 1.5 Registrar la decisión de poda con la evidencia de 1.1–1.4: qué lotes quedan justificados, cuáles se cierran como no justificados a esta escala y los valores elegidos para `ef_search`, timeout/ventana de lectura y la cota del TTL de identidad de D8; verificar que cada lote sobreviviente cita su número de base

## 2. Knobs vectoriales y vecinos indexables (D1, D2, D5)

- [x] 2.1 Mover `hnsw.iterative_scan` y `hnsw.ef_search` a `server_settings` en `_database_connect_args`, eliminar los `SET LOCAL` equivalentes de `memory_repo` y `skill_repo`, y verificar con un test de integración que una conexión del pool reporta los valores esperados y que la suite de retrieval sigue verde
- [x] 2.2 Reescribir `related_to` en dos pasos dentro de la misma transacción RLS (leer embedding/modelo de la semilla activa propia; vecinos con `ORDER BY embedding <=> semilla` y el mismo piso y regla de modelo) y verificar con los tests existentes que semilla desconocida/ajena/retirada sigue devolviendo lista vacía y que los vecinos servidos no cambian para el corpus de fixture
- [x] 2.3 Cambiar el orden del LATERAL de `_scalable_graph_edges` a distancia ascendente sólo si el `EXPLAIN` de 1.2 repetido muestra uso del índice o mejora clara; en caso contrario revertir el punto y dejar constancia del plan observado junto a esta tarea
- [x] 2.4 Correr el evaluador de ranking versionado antes/después del lote y anotar que `nDCG@5`, `essential-recall@3` e `irrelevant-rate@5` no regresan en ninguna etiqueta protegida

## 3. Menos consultas por llamada (D3, D6)

- [x] 3.1 Cargar los pools de búsqueda y de `context_snapshot` sin anclas (`noload`) y adjuntar las anclas de los ítems servidos con una única consulta por llamada, conservando `selectin` en `get_memory`/`list_memories`/historial; verificar que `recall` y `context` siguen devolviendo las anclas correctas y que el conteo de 1.3 baja según lo previsto
- [x] 3.2 Añadir el pre-chequeo de duplicado por hash antes de embeber en `remember` y la resolución de hashes en una consulta para `remember_batch` (embeber sólo faltantes), conservando la reverificación dentro de la transacción de escritura; verificar con un cliente de embeddings falso contador que un duplicado exacto no dispara ninguna llamada de embedding y que los tests de dedup/carrera existentes siguen verdes

## 4. Presupuesto de lectura para embeddings (D7)

- [x] 4.1 Añadir settings acotados de timeout de lectura y ventana negativa al cliente de embeddings y usarlos en `recall`, foco de `context` y `match_skills`, degradando a textual con el modo marcado al agotarse; verificar con un cliente falso lento y uno que falla que la lectura responde degradada dentro del presupuesto y que, vencida la ventana, vuelve a intentar y puede volver a híbrido
- [x] 4.2 Añadir una cache LRU acotada de embeddings de lectura por `(modelo, texto normalizado)` reutilizando el cliente existente sin dependencias nuevas; verificar con el cliente falso contador que una segunda consulta idéntica no realiza HTTP y que la cache respeta su tope
- [x] 4.3 Verificar que las escrituras (`remember`, `update`, `save_skill`) siguen usando el timeout completo, nunca quedan alcanzadas por la ventana negativa ni sirven vectores desde la cache de lectura, corriendo los tests de degradación en escritura existentes

## 5. Registro de uso diferido (D4)

- [x] 5.1 Crear el buffer de uso reutilizando el molde de `TelemetryBuffer` (acotado, un worker con lifecycle registrado en la app, volcado por tamaño o intervalo y volcado final en cierre ordenado) con settings acotados propios en el container; verificar con tests unitarios el volcado por lote, por intervalo y al detener
- [x] 5.2 Aplicar el lote por usuario con un único `UPDATE ... FROM unnest(...)` en su sesión RLS que sume `recall_count`/`context_count` y avance `last_recalled_at` sin retrocederlo ni tocar `memory_generation`; verificar con test de integración que dos servicios del mismo ítem acumulan y que un `recall` no invalida la generación del perfil
- [x] 5.3 Hacer que `recall` y `context` sólo encolen uso (eliminar los `await` de escritura del camino de respuesta) y que `context`/lectura de perfil vuelquen antes lo pendiente de ese usuario si lo hay; verificar con tests que el slice dynamic incluye una memoria recién servida por `recall` sin reconstruir el perfil y que un fallo de registro no altera las lecturas
- [x] 5.4 Exponer en la superficie de métricas los descartes por acotación y los fallos de aplicación del registro diferido, agregados y sin identificadores; verificar con test que forzar el desbordamiento del buffer hace observable el descarte sin exponer usuario ni memoria

## 6. Autenticación en una transacción y TTL medido (D8)

- [x] 6.1 Resolver lookup por hash y refresco de `last_used_at` en una misma sesión del repositorio de API keys cuando el refresco corresponde; verificar que los tests de autenticación existentes (incluido el refresco como máximo una vez por intervalo) siguen verdes y que el conteo de transacciones de una autenticación sin cache baja a una
- [x] 6.2 Fijar el default del TTL de identidad según la cota decidida en 1.5 y actualizar el comentario de configuración que lo declara demora máxima de revocación; verificar que los escenarios de revocación con cache en cero y con ventana opt-in de `mcp-agent-integration` siguen pasando

## 7. Lote de escalado (D9)

- [x] 7.1 Añadir la migración del índice parcial `(user_id, last_recalled_at DESC) WHERE deleted_at IS NULL AND last_recalled_at IS NOT NULL` con su downgrade y el `Index` equivalente en `models.py`; verificar que el `EXPLAIN` de la selección dynamic usa el índice nuevo y que la suite de integración de migraciones pasa
- [x] 7.2 Pedir en `context_snapshot` tops proporcionales al presupuesto efectivo (ítems pedidos + solape de perfil + 1) en vez del tope absoluto; verificar que los tests de presupuesto y de `omitted` por categoría siguen verdes sin cambiar ningún número servido
- [x] 7.3 Unificar generación, candidatos y upsert con CAS de `rebuild_profile` en una sola transacción por intento conservando el reintento acotado; verificar que los tests de perfil (conflicto de generación, lectura que nunca sirve perfil anterior a la última mutación) siguen verdes
- [x] 7.4 Colapsar `statistics()` a dos consultas conservando exactamente la forma de salida; verificar con los tests de administración/estadísticas existentes que cada agregado coincide con el cálculo anterior sobre el mismo fixture
- [x] 7.5 Reescribir `history()` como una CTE recursiva con guarda de ciclo conservando orden y semántica de árbol de supersesión; verificar con los tests de historial existentes (cadena lineal y fusión muchos-a-uno) que el resultado es idéntico

## 8. Presupuestos permanentes y cierre (D10)

- [x] 8.1 Dejar un test de regresión que afirma techos de statements por llamada para `recall`, `context` sin foco, `context` con foco y `context` tras `recall`, fijados con los números reales post-implementación; verificar que el test falla si se reintroduce una escritura sincrónica o una carga de anclas por pool
- [x] 8.2 Correr la suite completa del repositorio, los tests de integración contra PostgreSQL+pgvector y las gates configuradas del proyecto (lint y tipos) y dejar constancia de pasados/fallados/omitidos y código de salida
- [x] 8.3 Comparar contra la línea de base de la fase 1 (p95 por herramienta, planes `EXPLAIN`, conteos de statements y evaluador de ranking) y anotar el antes/después por lote, incluidos los lotes podados en 1.5 con su evidencia, como cierre del cambio

## Workflow follow-up

- Archivar el cambio con el flujo de archivo de OpenSpec una vez satisfechas las revisiones del proyecto.
- Verificar que los deltas archivados quedaron aplicados sobre `openspec/specs/agent-memory-retrieval` y `openspec/specs/agent-usage-telemetry`.
