## ADDED Requirements

### Requirement: Degradación uniforme de escritura ante embeddings no disponibles
Cuando el servicio de embeddings no está disponible, el guardado individual MUST degradar igual que el lote: la memoria MUST almacenarse con el marcador de embedding no disponible y el resultado MUST declarar que la escritura fue degradada. El sistema MUST NOT rechazar el guardado por indisponibilidad de embeddings mientras PostgreSQL esté operativo. Cuando el servicio de embeddings se recupera, el operador CAN reindexar los marcadores con el CLI de re-embed existente.

#### Scenario: Remember con Ollama caído
- **WHEN** un usuario guarda una memoria y el servicio de embeddings no responde
- **THEN** la memoria queda almacenada con marcador de embedding no disponible y el resultado declara la escritura degradada, sin error hacia el cliente

#### Scenario: Remember con Ollama disponible
- **WHEN** un usuario guarda una memoria y el servicio de embeddings funciona
- **THEN** la memoria se almacena con su embedding y el resultado no declara degradación

#### Scenario: Reindexación posterior recupera el embedding
- **WHEN** el operador ejecuta el CLI de re-embed tras una escritura degradada y el servicio de embeddings ya responde
- **THEN** la memoria pasa a tener embedding real sin cambios en su contenido

## MODIFIED Requirements

### Requirement: Captura por lotes
El sistema MUST permitir guardar varias memorias atómicas en una sola operación acotada, aplicando a
cada ítem las mismas validaciones, deduplicación y aviso de similares que al guardado individual, y
MUST devolver el resultado de cada ítem de forma independiente con éxito parcial. Cuando varios
ítems degradan por indisponibilidad de embeddings, el sistema MUST acotar el tiempo total del lote
solapando los reintentos en lugar de ejecutarlos en serie; los resultados por ítem no cambian.

#### Scenario: Lote válido
- **WHEN** un agente envía un lote dentro del límite con ítems válidos
- **THEN** cada ítem se persiste con su propio resultado, incluyendo deduplicación y similares por ítem

#### Scenario: Lote con un ítem inválido
- **WHEN** un ítem del lote es inválido o su embedding falla
- **THEN** ese ítem devuelve su resultado degradado o su error y los demás ítems se procesan igualmente

#### Scenario: Lote degradado con embeddings caídos
- **WHEN** todos los ítems de un lote degradan porque el servicio de embeddings no responde
- **THEN** el tiempo total de la operación es del orden de un único timeout, no de N timeouts en serie

#### Scenario: Lote fuera de límite
- **WHEN** el lote excede el máximo de ítems permitido o llega vacío
- **THEN** el sistema rechaza la operación completa sin persistir nada
