## ADDED Requirements

### Requirement: Filtro opcional por kind
`recall`, `list_memories` y `context` MUST aceptar un filtro opcional `kind`. Cuando está presente, el sistema MUST restringir el conjunto candidato a memorias con ese `kind`. Las memorias con `kind` nulo MUST NO coincidir con un filtro concreto. Ausencia del filtro MUST incluir todos los kinds.

#### Scenario: Recall de fallos
- **WHEN** `recall` se llama con `kind=failure`
- **THEN** el resultado no incluye memorias de otro kind ni las de kind nulo

#### Scenario: Sin filtro
- **WHEN** `recall` se llama sin `kind`
- **THEN** participan memorias de cualquier kind, incluidas las nulas
