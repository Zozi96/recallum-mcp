## Context

Estado actual (verificado sobre el código, no asumido):

- `MemoryService.remember` abre sesión y delega en `_remember_in_session` con el `embedding` ya resuelto por el llamador, o sin él (`service/src`: `remember` en `recallum/memory/service.py:284`). La capa MCP o el propio flujo de servicio resuelve el embedding antes de persistir; cuando `embed()` lanza `EmbeddingError` en la ruta individual, la excepción viaja hasta `mcp/errors.py`, que la traduce en el fallo MCP `embedding service unavailable` (contrato actual de `mcp-agent-integration`).
- `remember_batch` ya degrada: ante `EmbeddingError` por ítem persiste con el marcador `EMBEDDING_UNAVAILABLE_MESSAGE` y devuelve éxito por ítem (`service.py:490,540`). El fallback reintenta los embeddings por ítem en serie (`service.py:465-474`), así que un lote de N ítems con Ollama colgado paga N × `timeout_seconds` (30 s por defecto en `embeddings/ollama.py:24`).
- `recall` y `context` ya degradan a modo texto y lo declaran en la respuesta (`mode="degraded_textual"`, `service.py:967-973`).
- El CLI de re-embed permite reindexar marcadores posteriormente; es el mecanismo de reparación existente.

## Goals / Non-Goals

**Goals:**

- Comportamiento idéntico entre `remember` y `remember_batch` ante indisponibilidad de embeddings: guardar con marcador y declarar degradación en el resultado.
- Acotar el peor caso de latencia del lote degradado a O(timeout) en lugar de O(N·timeout).
- Hacer visible la degradación de escritura en telemetría con la misma señal que ya cubre la lectura.

**Non-Goals:**

- Reintento automático de embeddings en segundo plano tras guardar con marcador; el CLI de re-embed sigue siendo la vía de reparación.
- Alterar la traducción de errores MCP para fallos no relacionados con embeddings (`mcp/errors.py` queda intacto; ADR 0012 no se toca).
- Cambiar el contrato de `_similar_to`: el aviso de similares sigue siendo consultivo y fail-open.

## Decisions

1. **Degradar en el servicio, no en la capa MCP.** `MemoryService.remember` captura `EmbeddingError` donde hoy se produce el embedding, guarda con `EMBEDDING_UNAVAILABLE_MESSAGE` y marca el resultado con un campo de degradación (misma convención que `RecallResult.mode`). Alternativa considerada: traducir el error en la capa MCP a un resultado exitoso — rechazada, porque la degradación es semántica de dominio (afecta a web self-service y CLI también), no de transporte. Esto alinea la ruta individual con la regla ya aceptada para el lote y para las lecturas.

2. **Solapar los reintentos del lote con un semáforo.** Los reintentos de embedding por ítem se agrupan con `asyncio.gather` acotado por un semáforo (límite derivado del del cliente HTTP compartido). Alternativas: reintentar en serie (estado actual, rechazado por latencia lineal), o un único embedding por lote concatenado (rechazado: los embeddings se piden por texto normalizado por ítem y el marcado es por ítem).

3. **Un único campo discriminador de degradación.** Los resultados de escritura declaran `embedding_degraded: bool` (o reutilizan el literal existente si encaja, decisión final en diseño de esquema) en lugar de un enum compartido con lectura: lectura y escritura degradan de forma distinta (texto vs. marcador) y un tipo común forzaría estados imposibles. La telemetría registra el flag con la clase de operación, extendiendo el requisito existente.

4. **Reparación manual explícita.** El marcador sigue siendo reindexable exclusivamente por el CLI de re-embed. Añadir un reintento automático en background añadiría concurrencia sobre la sesión del usuario y un nuevo punto de fallo sin beneficio demostrado; las evaluaciones de retrieval ya muestran el impacto del modo texto.

## Risks / Trade-offs

- Los clientes que hoy tratan `embedding service unavailable` como señal de reintento pasan a recibir éxito degradado: el riesgo es silenciar memorias sin embedding. Mitigación: el resultado lo declara explícitamente y la telemetría lo registra, de modo que un operador puede detectar la proporción de escrituras degradadas.
- El solapamiento de reintentos aumenta la presión transitoria sobre Ollama durante su propia caída. Mitigación: semáforo acotado al límite del cliente HTTP; el caso dominante es fallo rápido (conexión rechazada), no timeout lento.
- `embedding_degraded` añade un campo al contrato de salida: compatible hacia atrás (campo aditivo), pero habrá que actualizar los esquemas de `tests/unit/test_mcp_tools_docs.py` (gate de drift de docstrings).
