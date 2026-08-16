## 1. Diseño de consulta

- [ ] 1.1 Elegir estrategia kNN/ANN sobre pgvector para vecinos por nodo bajo el techo `graph_max_neighbours`
- [ ] 1.2 Definir flag/umbral de activación (default off o documentado) sin romper pairwise actual

## 2. Implementación

- [ ] 2.1 Implementar path de aristas acotado en `graph_snapshot` (y alinear `related_to` si comparte semántica)
- [ ] 2.2 Preservar umbral de similitud, mismo modelo, sin aristas artificiales, truncado visible

## 3. Pruebas

- [ ] 3.1 Paridad de aristas en fixtures pequeños vs pairwise
- [ ] 3.2 Truncado y densidad: no inventar vecinos bajo el umbral

## 4. Verificación

- [ ] 4.1 Tests unitarios/integración de grafo en verde
- [ ] 4.2 Documentar cuándo activar el path escalable en operations/runbook
