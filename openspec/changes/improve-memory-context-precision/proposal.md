## Why

`recall` puede llenar el límite solicitado con candidatos débiles porque la fusión ordena los mejores vecinos disponibles sin exigir evidencia mínima de utilidad. Esto reduce la densidad de contexto: encontrar la memoria esencial no basta si el resto del presupuesto se consume con coincidencias irrelevantes, mientras que las memorias de soporte realmente útiles sí deben conservarse.

## What Changes

- Tratar `limit` y `max_tokens` como techos: `recall` podrá devolver menos resultados cuando los candidatos restantes no alcancen evidencia mínima calibrada de utilidad.
- Admitir candidatos antes de la fusión mediante señales existentes y umbrales medidos, preservando la degradación textual y sin añadir un reranker basado en LLM.
- Evaluar relevancia graduada —esencial, soporte, contextual e irrelevante— y medir `nDCG@5`, `essential-recall@3`, `irrelevant-rate@5` y densidad útil bajo presupuesto.
- Añadir negativos difíciles y casos multilingües al dataset versionado para calibrar la admisión sin perder contexto de soporte valioso.
- Mantener sin cambios el aislamiento por usuario/proyecto, los filtros, los presupuestos, el orden por estrategia y los valores por defecto de los votos de uso y frescura.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-retrieval`: exigir utilidad mínima para servir resultados, permitir respuestas por debajo del límite y ampliar el contrato de evaluación con relevancia graduada y métricas de ruido contextual.

## Impact

- Afecta el conjunto final de resultados de `recall` y los candidatos enfocados que `context(focus=...)` obtiene mediante la misma recuperación híbrida.
- Afecta la consulta vectorial, la admisión previa a RRF, los límites/configuración de recuperación y el evaluador/dataset de ranking.
- No cambia el esquema público de las respuestas MCP, la persistencia de memorias, el modelo de embeddings por defecto ni las dependencias externas.
- El cambio es compatible para clientes: los campos permanecen iguales, pero una llamada puede devolver menos ítems que antes cuando el resto sea irrelevante.
