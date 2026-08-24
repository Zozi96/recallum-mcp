## 1. Estimador y límites

- [ ] 1.1 Añadir `max_tokens` a `MemoryLimits` (cap de servidor) y un estimador determinista `ceil(chars/4)+overhead`; verificar con tests unitarios de casos vacíos, cortos y que cruzan el umbral
- [ ] 1.2 Documentar en el docstring de `recall`/`context` que el recuento es una estimación, no tokens del modelo cliente

## 2. Empaquetado de recall

- [ ] 2.1 Aplicar packing post-RRF en `MemoryService.recall` cuando `max_tokens` está presente; verificar que sin el argumento el `limit` se comporta como hoy
- [ ] 2.2 Rechazar `strategy` desconocida con `MemoryValidationError`; verificar el mensaje

## 3. Estrategias

- [ ] 3.1 Implementar el reorder estable por prioridad de categoría según design.md; verificar un fixture debugging (facts antes que preferences) y que un único hit de otra categoría no se descarta
- [ ] 3.2 Aplicar la misma estrategia al remainder de `context` sin desalojar el perfil; verificar con `test_context_budget`

## 4. Superficie MCP/HTTP

- [ ] 4.1 Añadir args opcionales a tools MCP y self-service; verificar contrato de schemas (`test_mcp_tools_docs` / unit tools)
- [ ] 4.2 Suite unitaria relevante en verde (`tests/unit/test_service.py`, `tests/unit/test_context_budget.py`)
