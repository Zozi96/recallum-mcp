## ADDED Requirements

### Requirement: Anclas de código opcionales
Una memoria MUST poder asociarse a cero o más anclas, cada una con tipo `file`, `symbol` o `module` y un identificador verbatim. El sistema MUST NOT exigir anclas para guardar una memoria. El sistema MUST NOT construir ni almacenar un grafo de llamadas, ASTs ni repositorios indexados como condición de este requisito.

#### Scenario: Decisión anclada a un símbolo
- **WHEN** un usuario guarda una memoria con ancla `symbol=PaymentService.capture`
- **THEN** la memoria queda asociada a ese identificador y las lecturas lo exponen

#### Scenario: Sin anclas
- **WHEN** `remember` omite anclas
- **THEN** la memoria se guarda igual que hoy
