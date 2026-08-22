## MODIFIED Requirements

### Requirement: Grafo acotado y honesto
El sistema MUST limitar el número de nodos y de relaciones para mantener una respuesta y visualización manejables, MUST priorizar las relaciones temáticas más fuertes y MUST indicar el total disponible y si la lectura fue truncada. Los límites MUST NOT provocar conexiones artificiales. Cuando el volumen de candidatos o la configuración lo requieran, el sistema MAY calcular vecinos por búsqueda acotada por nodo (kNN/ANN) en lugar de una comparación pairwise completa, siempre que preserve el umbral mínimo de similitud, la comparabilidad sólo entre embeddings del mismo modelo, y la ausencia de aristas decorativas.

#### Scenario: Memoria dentro del límite
- **WHEN** todas las memorias candidatas caben en el límite efectivo
- **THEN** la respuesta indica que el grafo no fue truncado

#### Scenario: Memoria mayor que el límite
- **WHEN** existen más memorias candidatas que las permitidas
- **THEN** el sistema devuelve un subconjunto determinista, comunica el total y marca la respuesta como truncada

#### Scenario: Componente muy denso
- **WHEN** un nodo supera el máximo de vecinos presentables
- **THEN** el sistema conserva sus relaciones más fuertes dentro del límite

#### Scenario: Nodo sin relación suficiente
- **WHEN** ninguna relación de un nodo supera la evidencia mínima
- **THEN** el nodo permanece visible sin que el sistema le asigne un vecino artificial

#### Scenario: Vecinos por búsqueda acotada
- **WHEN** la proyección usa kNN/ANN por nodo bajo el techo de vecinos
- **THEN** cada arista cumple el umbral mínimo de similitud y el mismo modelo de embedding, y el truncado global sigue comunicándose
