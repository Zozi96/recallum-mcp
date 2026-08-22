## 1. Diseño de consulta

- [x] 1.1 Elegir estrategia kNN/ANN sobre pgvector para vecinos por nodo bajo el techo `graph_max_neighbours`
- [x] 1.2 Definir flag/umbral de activación (default off o documentado) sin romper pairwise actual

## 2. Implementación

- [x] 2.1 Implementar path de aristas acotado en `graph_snapshot` (y alinear `related_to` si comparte semántica)
- [x] 2.2 Preservar umbral de similitud, mismo modelo, sin aristas artificiales, truncado visible

## 3. Pruebas

- [x] 3.1 Paridad de aristas en fixtures pequeños vs pairwise
- [x] 3.2 Truncado y densidad: no inventar vecinos bajo el umbral

## 4. Verificación

- [x] 4.1 Tests unitarios/integración de grafo en verde
- [x] 4.2 Documentar cuándo activar el path escalable en operations/runbook
