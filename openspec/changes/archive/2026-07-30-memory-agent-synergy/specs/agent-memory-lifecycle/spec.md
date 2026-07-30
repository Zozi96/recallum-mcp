# Agent Memory Lifecycle (delta)

## MODIFIED Requirements

### Requirement: Deduplicación exacta
El sistema MUST evitar memorias activas duplicadas para el mismo usuario, ámbito y contenido
normalizado, y MUST registrar la fecha de reconfirmación cuando un contenido idéntico vuelve a
guardarse, exponiéndola en las respuestas como señal de frescura.

#### Scenario: Recordar el mismo hecho dos veces
- **WHEN** un usuario guarda nuevamente una memoria activa con el mismo contenido normalizado y ámbito
- **THEN** el sistema devuelve la memoria existente y no crea una segunda fila

#### Scenario: Reconfirmación con huella temporal
- **WHEN** un contenido idéntico a una memoria activa vuelve a guardarse
- **THEN** la memoria existente registra la fecha de reconfirmación y las respuestas posteriores la incluyen

## ADDED Requirements

### Requirement: Aviso de similares sin distinción de categoría
Al crear una memoria, el sistema MUST reportar las memorias activas preexistentes del mismo ámbito y
proyecto que traten el mismo asunto aunque estén archivadas bajo otra categoría, identificando la
categoría de cada similar; el aviso MUST ser únicamente informativo y su fallo MUST NOT impedir la
escritura.

#### Scenario: Similar en otra categoría
- **WHEN** se guarda como `fact` un contenido muy similar a una `decision` activa del mismo ámbito
- **THEN** la respuesta reporta esa memoria como similar indicando su categoría

#### Scenario: Fallo del aviso
- **WHEN** la detección de similares falla tras persistir la memoria
- **THEN** la memoria queda guardada y la respuesta omite el aviso sin error

### Requirement: Captura por lotes
El sistema MUST permitir guardar varias memorias atómicas en una sola operación acotada, aplicando a
cada ítem las mismas validaciones, deduplicación y aviso de similares que al guardado individual, y
MUST devolver el resultado de cada ítem de forma independiente con éxito parcial.

#### Scenario: Lote válido
- **WHEN** un agente envía un lote dentro del límite con ítems válidos
- **THEN** cada ítem se persiste con su propio resultado, incluyendo deduplicación y similares por ítem

#### Scenario: Lote con un ítem inválido
- **WHEN** un ítem del lote es inválido o su embedding falla
- **THEN** ese ítem devuelve su error y los demás ítems se procesan igualmente

#### Scenario: Lote fuera de límite
- **WHEN** el lote excede el máximo de ítems permitido o llega vacío
- **THEN** el sistema rechaza la operación completa sin persistir nada
