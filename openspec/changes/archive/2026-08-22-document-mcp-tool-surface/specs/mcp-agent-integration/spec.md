## ADDED Requirements

### Requirement: Documentación pública alineada con la superficie MCP
La documentación de entrada del repositorio (como mínimo el README principal y cualquier guía de clientes que enumere herramientas MCP) MUST listar exactamente las mismas herramientas que el servidor anuncia: `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm` y `forget`. MUST NOT afirmar un conteo u omisión que contradiga ese conjunto.

#### Scenario: README enumera la superficie
- **WHEN** un operador lee el README del servicio MCP
- **THEN** aparecen las once herramientas por nombre, sin afirmar que son nueve ni omitir `related_memories` o `reconfirm`

#### Scenario: Guía de clientes coherente
- **WHEN** una guía de cliente documentada enumera herramientas MCP
- **THEN** usa el mismo conjunto de once nombres que el anuncio del servidor
