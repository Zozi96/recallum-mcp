# MCP Agent Integration (delta)

## MODIFIED Requirements

### Requirement: Conjunto mínimo de herramientas
El sistema MUST publicar exactamente las capacidades de guardado individual y por lotes,
recuperación, contexto con foco opcional, enumeración, corrección y borrado mediante las
herramientas `remember`, `remember_batch`, `recall`, `context`, `list_memories`, `update` y
`forget`.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia las siete herramientas con esquemas de entrada y salida validados

#### Scenario: Contexto con foco
- **WHEN** un cliente inspecciona el esquema de `context`
- **THEN** el esquema acepta un foco de tarea opcional además del proyecto y los límites de presupuesto
