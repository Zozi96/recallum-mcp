## 1. Contract

- [x] 1.1 Reemplazar el comentario de `MemoryLimits.recall_vector_min_similarity` que habla de calibración pendiente: el default medido es `None`. Verificar que `uv run pytest tests/unit/test_service.py::test_recall_vector_min_similarity_defaults_disabled_and_is_capped` sigue pasando.
- [x] 1.2 Confirmar que ningún docstring o ayuda de herramienta MCP afirma utilidad calibrada en el resultado fusionado. Verificar con `uv run pytest tests/unit/test_mcp_tools.py`.

## 2. Close

- [x] 2.1 Validar el change: `openspec validate align-useful-density-spec --strict`.
