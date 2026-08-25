## 1. Persistencia

- [x] 1.1 Migración `skills` (RLS, HNSW, GIN tsvector, unique parcial de nombre activo por bucket, `superseded_by`); verificar upgrade
- [x] 1.2 Repositorio + servicio (save, match híbrido, get, forget, dedup de pasos); verificar aislamiento y degradación textual

## 2. MCP

- [x] 2.1 Registrar `save_skill`, `match_skills`, `get_skill`, `forget_skill`; verificar que el listado de tools pasa a quince y el grafo sigue oculto
- [x] 2.2 Actualizar `test_mcp_tools_docs.py`, prompts/skill del plugin (cuándo skill vs memory) y el recuento allowlisteado

## 3. Calidad

- [x] 3.1 Similar advisory al guardar; verificar que no auto-fusiona skills
- [x] 3.2 Tests unitarios/integración de skills en verde; ruff en archivos tocados
