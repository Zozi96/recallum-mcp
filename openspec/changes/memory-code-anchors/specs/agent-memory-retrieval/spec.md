## ADDED Requirements

### Requirement: Filtro por símbolo o archivo
`recall` MUST aceptar `symbol` y/o `file` opcionales. Cuando están presentes, el conjunto candidato MUST restringirse a memorias que tengan un ancla coincidente (igualdad normalizada: trim, NFC) **antes** de fusionar señales. El texto de la consulta MUST seguir pudiendo usarse sobre ese subconjunto. Ausencia de filtro MUST no exigir anclas.

#### Scenario: Recall por símbolo
- **WHEN** `recall` se llama con `symbol=PaymentService.capture`
- **THEN** el resultado sólo incluye memorias ancladas a ese símbolo (del usuario, activas)

#### Scenario: Símbolo sin memorias
- **WHEN** no hay anclas coincidentes
- **THEN** el resultado está vacío aunque existan memorias semánticamente similares sin ancla

#### Scenario: Consulta libre sigue funcionando
- **WHEN** `recall` se llama con query `PaymentService.capture` sin filtro `symbol`
- **THEN** las piernas FTS y trigram existentes pueden devolver memorias que mencionan el identificador en el contenido, tengan o no ancla
