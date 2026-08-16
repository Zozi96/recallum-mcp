## Why

`graph_snapshot` calcula pares por comparación pairwise O(n²) con techo conservador (~1k nodos). Eso es correcto hoy, pero se vuelve techo duro cuando un usuario se acerque a ese volumen. El `ponytail` del código ya nombra el upgrade: aristas por kNN/ANN por nodo.

## What Changes

- Permitir que la proyección del grafo obtenga vecinos por búsqueda acotada por nodo (kNN/ANN) en lugar de pairwise completo cuando el volumen lo requiera.
- Conservar honestidad: mismos umbrales de similitud mínima, sin aristas decorativas, truncado visible, y comparabilidad sólo entre embeddings del mismo modelo.
- Activación condicionada a evidencia de tamaño o a configuración explícita; el comportamiento actual pairwise permanece válido bajo el techo actual.
- Mantener fuera de alcance: rediseño visual de la UI del grafo, herramientas MCP de grafo completo, y ranking de `recall`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `memory-graph`: Estrategia de aristas escalable (kNN/ANN acotado) compatible con grafo acotado y honesto, sin inventar relaciones.

## Impact

- Afecta `MemoryRepository.graph_snapshot` / `related_to`, límites en `MemoryLimits`, y pruebas de grafo.
- Puede requerir índice/consulta pgvector adicional; no cambia RLS ni contenido expuesto.
