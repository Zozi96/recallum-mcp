## 1. Degradación uniforme en la ruta individual

- [x] 1.1 Añadir el campo de degradación a los esquemas de resultado de escritura en `recallum/memory/schemas.py` (campo aditivo, por defecto `False`). Verificación: `tests/unit/test_models.py` pasa y el campo aparece en la serialización.
- [x] 1.2 En `MemoryService.remember` / `_remember_in_session` (`recallum/memory/service.py`), capturar `EmbeddingError` en el punto donde se genera el embedding y persistir con el marcador `EMBEDDING_UNAVAILABLE_MESSAGE`, devolviendo el resultado con degradación declarada. Escribir primero el test que falle: `remember` con embeddings caídos hoy lanza `EmbeddingError`; tras el cambio debe devolver éxito degradado. Verificación: nuevo caso en `tests/unit/test_service.py` pasa y el caso previo de error en `tests/unit/test_mcp_errors.py` se actualiza.
- [x] 1.3 Revisar que `_similar_to` sigue fail-open cuando el embedding es marcador (no debe lanzar HNSW con vector ausente). Verificación: test de `remember` con Ollama caído no produce warning de similares ni fallo.

## 2. Concurrencia acotada en el fallback del lote

- [x] 2.1 Solapar los reintentos de embedding por ítem en `remember_batch` con `asyncio.gather` y semáforo acotado al límite del cliente HTTP compartido. Escribir primero el test: lote de N ítems con embeddings lentos debe completar en ~O(timeout), no N·timeout. Verificación: test de timing acotado en `tests/unit/test_service.py` pasa y `tests/unit/test_agent_synergy.py` sigue verde.
- [x] 2.2 Confirmar que el orden y el contenido de los resultados por ítem no cambian respecto a la ejecución en serie. Verificación: los tests existentes de captura por lotes pasan sin modificar sus aserciones de resultado.

## 3. Telemetría y contrato MCP

- [x] 3.1 Registrar la degradación de escritura en la capa de telemetría (`recallum/telemetry/`) distinguiendo lectura de escritura según el requisito modificado. Verificación: caso nuevo en `tests/unit/test_telemetry.py`.
- [x] 3.2 Actualizar los docstrings de `remember`/`remember_batch` en `recallum/mcp/server.py` y el gate de drift `tests/unit/test_mcp_tools_docs.py` para reflejar que un fallo de embeddings devuelve resultado degradado. Verificación: `test_mcp_tools_docs.py` pasa.
- [x] 3.3 Verificar que el escenario de `mcp/errors.py` para operaciones sin degradación sigue devolviendo `embedding service unavailable` exacto. Verificación: `tests/unit/test_mcp_errors.py` pasa con el caso reenfocado a una operación sin degradación.

## 4. Validación global

- [x] 4.1 Ejecutar `uv run pytest tests/unit -q` completo y corregir regresiones. Verificación: suite unitaria verde.
- [ ] 4.2 Ejecutar la integración relevante (`tests/integration/test_db.py` y contrato de repositorio) si hay base de datos disponible. Verificación: tests de integración verdes o marcados según su marker si no hay PostgreSQL.
- [x] 4.3 Resolver los supresores de tipado de `recallum/memory/service.py` (`[assignment]`, `[arg-type]`, `[return]` en la baseline de mypy) al completar la degradación uniforme. Verificación: `uv run mypy recallum` sin esos supresores.
