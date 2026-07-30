# Web Self-Service API (delta)

## MODIFIED Requirements

### Requirement: Creación de memorias con aviso de similares
El sistema MUST permitir crear una memoria propia y MUST devolver junto a ella las memorias
similares detectadas en el mismo ámbito y proyecto sin filtrar por categoría, identificando la
categoría de cada similar y sin resolver automáticamente ninguna contradicción.

#### Scenario: Creación sin similares
- **WHEN** se crea una memoria que no se parece a ninguna existente
- **THEN** el sistema la almacena y devuelve una lista vacía de similares

#### Scenario: Creación con similares
- **WHEN** se crea una memoria parecida a otras ya existentes
- **THEN** el sistema la almacena y devuelve las similares para que la persona decida si sustituir alguna

#### Scenario: Similar bajo otra categoría
- **WHEN** se crea una memoria muy parecida a otra activa archivada bajo una categoría distinta
- **THEN** el sistema la reporta como similar indicando su categoría

#### Scenario: Contenido duplicado exacto
- **WHEN** el contenido coincide exactamente con una memoria activa del mismo ámbito
- **THEN** el sistema no crea un duplicado y lo comunica

#### Scenario: Datos inválidos
- **WHEN** la categoría, la importancia, el ámbito o la metadata no son válidos
- **THEN** el sistema rechaza la creación indicando qué campo es incorrecto

### Requirement: Consulta de una memoria concreta
El sistema MUST permitir obtener una memoria propia por su identificador y MUST responder de forma
idéntica ante un identificador inexistente y uno perteneciente a otro usuario.

#### Scenario: Memoria propia
- **WHEN** se solicita una memoria del usuario de la sesión
- **THEN** el sistema devuelve su contenido, categoría, ámbito, proyecto, importancia, metadata, fecha de creación y, cuando existen, sus señales de reconfirmación y de uso

#### Scenario: Identificador ajeno o inexistente
- **WHEN** se solicita una memoria de otro usuario o un identificador que no existe
- **THEN** el sistema responde de la misma manera en ambos casos, sin revelar cuál es

## ADDED Requirements

### Requirement: Reasignación de proyecto
El sistema MUST permitir mover en una sola operación todas las memorias activas del usuario desde
una clave de proyecto hacia otra, MUST excluir de la operación las memorias cuyo contenido ya existe
activo en el proyecto destino reportándolas como colisiones, y MUST NOT modificar ámbito, contenido
ni embeddings de las memorias movidas.

#### Scenario: Migración de clave de proyecto
- **WHEN** el usuario solicita reasignar sus memorias de una clave de proyecto a otra distinta
- **THEN** el sistema mueve las memorias activas sin colisión y responde cuántas movió

#### Scenario: Colisiones de contenido
- **WHEN** el proyecto destino ya contiene una memoria activa con el mismo contenido normalizado
- **THEN** la memoria de origen no se mueve y la respuesta la identifica como colisión

#### Scenario: Claves inválidas
- **WHEN** la clave de origen y la de destino son iguales, o alguna es vacía o inválida
- **THEN** el sistema rechaza la operación sin modificar ninguna memoria
