## ADDED Requirements

### Requirement: Proyección de vecinos desde una semilla
El sistema MUST poder devolver los vecinos temáticos de una memoria activa a partir de la misma evidencia de similitud que el grafo (embeddings almacenados comparables y umbral mínimo), filtrados a esa semilla. La proyección MUST NOT incluir embeddings ni el conjunto completo de nodos y aristas del grafo. La categoría, el ámbito y el proyecto MUST NOT impedir un vecino ni crearlo por sí solos. El número de vecinos MUST estar acotado.

#### Scenario: Vecinos de una memoria puente
- **WHEN** se solicitan los vecinos de una memoria similar a otras de proyectos o categorías distintos
- **THEN** esos vecinos aparecen con su similitud y no aparecen memorias que no alcancen el umbral

#### Scenario: Semilla sin vecinos comparables
- **WHEN** la semilla no tiene embeddings comparables o ninguna otra memoria supera el umbral
- **THEN** la proyección de vecinos está vacía

#### Scenario: Aislamiento
- **WHEN** otra cuenta tiene memorias temáticamente cercanas a la semilla
- **THEN** no aparecen en la proyección de vecinos
