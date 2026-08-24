## ADDED Requirements

### Requirement: Campos de procedencia en tools de escritura y lectura
`remember` y cada ítem de `remember_batch` MUST aceptar `source_type` y `source_ref` opcionales. Las representaciones de memoria devueltas por las tools de lectura MUST incluir esos campos. Omitirlos MUST ser válido.

#### Scenario: Remember con source_type
- **WHEN** un cliente autenticado llama `remember` con `source_type=bootstrap`
- **THEN** la memoria creada o deduplicada expone `source_type=bootstrap`

#### Scenario: Omitidos
- **WHEN** un cliente llama `remember` sin esos campos
- **THEN** la llamada es válida y `source_type` queda en `unknown`
