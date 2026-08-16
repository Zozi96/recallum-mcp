## Context

`graph_snapshot` hace pairwise O(n²) con `graph_max_nodes` ≤ 2000 (default 1000). El techo es deliberado. El upgrade natural es kNN/ANN por nodo con el mismo umbral de similitud y mismo modelo.

## Goals / Non-Goals

**Goals:**
- Permitir estrategia de aristas por búsqueda acotada por nodo sin inventar relaciones.
- Conservar truncado honesto, umbral mínimo y comparabilidad de modelo.
- Activación por volumen/config, sin romper el path pairwise actual bajo techo bajo.

**Non-Goals:**
- Rediseño visual UI, MCP tool de grafo completo, cambios a ranking de recall.
- Eliminar el techo de nodos presentados (sigue habiendo proyección acotada).

## Decisions

- **Dual-path**: pairwise para N pequeño; kNN/ANN cuando N o flag lo indiquen. Criterio inicial: config explícita o N sobre umbral configurable.
- **pgvector**: preferir consulta de vecinos por embedding existente antes de nueva dependencia.
- **related_to / MCP related_memories**: alinear semántica de vecinos con la misma estrategia cuando aplique, para no diverger grafo vs related.

## Risks / Trade-offs

- [Calidad de aristas distinta entre paths] → Mismos umbrales y tests de paridad en fixtures pequeños.
- [Coste de índices] → Medir antes de exigir índice IVFFlat/HNSW en todos los deploys; puede ser query order-by distance limit k sobre el subset seleccionado.

## Migration Plan

1. Implementar path kNN acotado detrás de flag/umbral.
2. Tests de paridad en grafos pequeños + truncado en densos.
3. Activar en producción sólo con evidencia de tamaño o flag de operador.

## Open Questions

- ¿Umbral de conmutación por defecto o sólo flag opt-in al principio? Default propuesto: **flag opt-in + umbral documentado**, default off para no cambiar comportamiento de usuarios actuales.
