## ADDED Requirements

### Requirement: Kind en tools
`remember`, ítems de `remember_batch`, `update` (atributos), `recall`, `list_memories` y `context` MUST aceptar `kind` opcional. Las representaciones de memoria MUST incluir `kind` (nulo cuando no está clasificado). El conjunto de tools MUST permanecer el mismo; no se añade una tool nueva.

#### Scenario: Remember con kind
- **WHEN** un cliente llama `remember` con `kind=solution`
- **THEN** la respuesta incluye `kind=solution`

#### Scenario: Compatibilidad
- **WHEN** un cliente omite `kind` en todas las tools
- **THEN** las llamadas siguen siendo válidas
