## Why

El requisito archivado **Densidad útil de resultados recuperados** afirma que `recall` y `context(focus=...)` sirven únicamente memorias con evidencia mínima calibrada. Dos matrices real-stack (2026-08-30) no encontraron un `recall_vector_min_similarity` que baje `irrelevant-rate@5` sin romper las guardas de idioma; el default de producción es `None`. El contrato publicado es falso: hay que alinearlo ahora, no dejarlo como promesa incumplida.

## What Changes

- Reescribir **Densidad útil** para que “configuración respaldada por el evaluador” incluya explícitamente **ningún piso vectorial** (`None`) como resultado calibrado, no como TODO pendiente.
- Acotar el piso opcional a la **pierna vectorial**. FTS y trigram conservan sus predicados. Una memoria admitida por cualquier pierna válida sigue pudiendo entrar en RRF.
- Corregir los escenarios que asumen admisión global (no rellenar el límite, lista vacía si no hay “utilidad”) para que valgan **cuando el piso vectorial está configurado**, y añadir el escenario de default: vecinos vectoriales débiles MAY aparecer; un negativo difícil admitido por FTS MUST NOT desaparecer sólo porque su cosine sea bajo.
- MUST NOT reabrir AND de FTS, retcon de `irr@5`, reranker LLM, ni exposición del piso al agente. Ranking/RRF queda fuera: este change no intenta ganar densidad, sólo deja de afirmarla.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-retrieval`: el requisito **Densidad útil de resultados recuperados** deja de exigir utilidad calibrada en el resultado fusionado; documenta techos `limit`/`max_tokens`, piso vectorial opcional, default `None` respaldado por el evaluador, y que FTS/trigram no están sujetos a ese piso.

## Impact

- Spec de recuperación y, si el comentario de `MemoryLimits.recall_vector_min_similarity` sigue hablando de calibración pendiente, ese texto.
- No cambia el comportamiento de `recall`/`context`, el evaluador, el dataset, FTS, RRF ni la superficie MCP.
- Compatible para clientes: las respuestas ya podían incluir vecinos débiles; el spec pasa a admitirlo.
