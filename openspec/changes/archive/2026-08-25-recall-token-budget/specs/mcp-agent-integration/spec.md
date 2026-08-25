## ADDED Requirements

### Requirement: Argumentos opcionales de presupuesto y estrategia
Las herramientas `recall` y `context` MUST aceptar `max_tokens` y `strategy` opcionales con la semántica del presupuesto de recuperación. Omitirlos MUST ser válido y MUST preservar el contrato actual. El sistema MUST NOT exigir un identificador de usuario en esos argumentos.

#### Scenario: Recall con presupuesto
- **WHEN** un cliente autenticado llama `recall` con `query`, `max_tokens` y `strategy`
- **THEN** el servidor aplica el empaquetado correspondiente y devuelve el resultado habitual (`query`, `mode`, `results`)

#### Scenario: Compatibilidad hacia atrás
- **WHEN** un cliente llama `recall` o `context` sin `max_tokens` ni `strategy`
- **THEN** la llamada es válida y el comportamiento coincide con el contrato previo a este change
