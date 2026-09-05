## Why

El comportamiento ante la caída del servicio de embeddings (Ollama) es inconsistente entre superficies: `recall` degrada a modo textual, `remember_batch` almacena los ítems con marcador `EMBEDDING_UNAVAILABLE_MESSAGE`, pero `remember` falla la llamada entera cuando el embedding no se puede generar, y el fallback del lote se ejecuta en serie (N ítems × timeout embeddings), multiplicando la latencia. Un agente cliente no puede predecir si guardar una memoria funcionará o no durante la misma caída.

## What Changes

- `remember` degrada al igual que `remember_batch`: cuando el servicio de embeddings no está disponible, la memoria se guarda con marcador de embedding no disponible y el resultado declara el estado degradado, en lugar de fallar con `embedding service unavailable`.
- Los errores de embeddings pasan de fail-closed a degradación explícita y visible en el resultado de la escritura, de forma coherente con la degradación textual ya existente en `recall` y `context`.
- El fallback del lote se ejecuta con concurrencia acotada (los reintentos por ítem se solapan en lugar de pagar N timeouts en serie); los resultados por ítem no cambian.
- La telemetría registra la degradación por embeddings también en las escrituras, no sólo en las recuperaciones.

## Capabilities

### New Capabilities

(ninguna)

### Modified Capabilities

- `agent-memory-lifecycle`: el guardado individual deja de fallar cuando el embedding no está disponible; degrada con marcador como el lote. El fallback del lote gana concurrencia acotada sin cambiar sus resultados.
- `agent-usage-telemetry`: el registro de degradación por embeddings se extiende a las rutas de escritura.
- `mcp-agent-integration`: el escenario "Servicio de embeddings no disponible" de `Confidencialidad de errores MCP` cambia: un fallo de embeddings en `remember` ya no produce el fallo MCP `embedding service unavailable`; ese mensaje queda reservado a fallos donde la degradación no aplica.

## Impact

- Código: `recallum/memory/service.py` (`remember`, `_remember_in_session`, `remember_batch`, `_similar_to`), `recallum/mcp/server.py` (traducción de errores intocable — el cambio afecta a cuándo se lanza), `recallum/memory/schemas.py` (campo de degradación en resultados de escritura).
- Tests: `tests/unit/test_service.py`, `tests/unit/test_mcp_errors.py`, `tests/unit/test_agent_synergy.py`, contratos de integración.
- Compatibilidad: los clientes que hoy reintentan `remember` ante fallo de embeddings pasan a recibir éxito degradado; el contenido almacenado sigue siendo reindexable vía el CLI de re-embed.
- No hay migraciones de base de datos.
