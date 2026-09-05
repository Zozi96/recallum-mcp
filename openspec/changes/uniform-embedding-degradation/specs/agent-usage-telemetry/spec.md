## MODIFIED Requirements

### Requirement: Registro de la degradación por embeddings
El sistema MUST registrar cuándo una operación se sirvió únicamente con ranking textual, o se completó con embedding marcador, por indisponibilidad del servicio de embeddings. El registro MUST distinguir la degradación en lectura de la degradación en escritura.

#### Scenario: Servicio disponible
- **WHEN** una operación usa ranking semántico y textual, o escribe con embedding real
- **THEN** la actividad no se marca como degradada

#### Scenario: Servicio no disponible
- **WHEN** una recuperación se sirve sólo con ranking textual
- **THEN** la actividad se marca como degradada en lectura

#### Scenario: Servicio no disponible en escritura
- **WHEN** un guardado se completa con marcador de embedding no disponible
- **THEN** la actividad se marca como degradada en escritura
