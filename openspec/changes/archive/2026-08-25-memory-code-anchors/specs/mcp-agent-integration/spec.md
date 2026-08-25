## ADDED Requirements

### Requirement: Anclas en remember y recall
`remember` y cada ítem de `remember_batch` MUST aceptar una lista opcional de anclas `{type, identifier}`. `recall` MUST aceptar `symbol` y `file` opcionales. El número de tools MCP MUST no cambiar por este change.

#### Scenario: Remember con ancla
- **WHEN** un cliente llama `remember` con una ancla `file=src/domain/users.py`
- **THEN** la memoria persistida incluye esa ancla

#### Scenario: Recall filtrado
- **WHEN** un cliente llama `recall` con `symbol` y `query`
- **THEN** la búsqueda se restringe a memorias ancladas a ese símbolo
