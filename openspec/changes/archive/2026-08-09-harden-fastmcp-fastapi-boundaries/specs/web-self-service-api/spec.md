## MODIFIED Requirements

### Requirement: Búsqueda híbrida de memorias propias
El sistema MUST permitir buscar entre las memorias propias combinando relevancia semántica y textual, MUST indicar cuándo el resultado proviene únicamente del ranking textual y MUST ofrecer como contrato canónico un `POST` cuyo término de búsqueda viaja en el cuerpo. El endpoint GET previo MUST conservar la misma autorización y resultados durante su ventana de deprecación, MUST anunciar su retiro y MUST NOT provocar que la consulta se registre.

#### Scenario: Búsqueda con embeddings disponibles
- **WHEN** se busca una consulta y el servicio de embeddings responde
- **THEN** el sistema devuelve resultados ordenados por la fusión de ambos rankings

#### Scenario: Búsqueda degradada
- **WHEN** el servicio de embeddings no está disponible
- **THEN** el sistema devuelve resultados textuales e indica que la búsqueda está degradada

#### Scenario: Sin coincidencias
- **WHEN** ninguna memoria coincide con la consulta
- **THEN** el sistema devuelve un resultado vacío y no un error

#### Scenario: Búsqueda canónica privada
- **WHEN** una sesión válida envía la consulta en el cuerpo de `POST /me/memories/search`
- **THEN** el sistema procesa la búsqueda sin colocar su contenido en la URL, access log ni métrica

#### Scenario: Cliente usa el GET deprecado
- **WHEN** una sesión válida usa el endpoint GET de búsqueda durante la ventana de migración
- **THEN** recibe resultados equivalentes junto con headers y metadatos OpenAPI de deprecación, sin que el query string sea registrado

### Requirement: Contrato de la API publicado
El sistema MUST publicar la descripción de la API web como artefacto versionado en el repositorio, MUST detectar cuando el artefacto deja de corresponderse con la implementación y MUST describir la cookie de sesión, la condición pública o protegida de cada operación y sus respuestas operativas relevantes.

#### Scenario: Contrato al día
- **WHEN** se comprueba el contrato publicado frente a la implementación
- **THEN** la comprobación pasa y el esquema contiene `APIKeyCookie` para cada ruta protegida mientras login permanece público

#### Scenario: API modificada sin regenerar el contrato
- **WHEN** cambia la API y no se actualiza el artefacto
- **THEN** la comprobación falla indicando la divergencia

#### Scenario: Errores operativos documentados
- **WHEN** una operación puede responder por autenticación, autorización, validación, tamaño, límite de tasa o dependencia no disponible
- **THEN** OpenAPI incluye los status aplicables entre `401`, `403`, `413`, `422`, `429` y `503` con un cuerpo estable

## ADDED Requirements

### Requirement: Tipos críticos consistentes en la API web
El sistema MUST reutilizar los mismos tipos estrictos y rangos de dominio para campos críticos expuestos por FastAPI, FastMCP y servicios de dominio.

#### Scenario: Coerción booleana inválida
- **WHEN** una ruta web recibe un booleano en un campo entero crítico como `importance`, `limit` u `offset`
- **THEN** responde `422` y no invoca el servicio de memoria

#### Scenario: Payload equivalente por web y MCP
- **WHEN** el mismo valor crítico válido se envía por ambos transportes
- **THEN** ambos aceptan el mismo rango y entregan el mismo valor al dominio

