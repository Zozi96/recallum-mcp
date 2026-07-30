# web-self-service-api Specification

## Purpose
Definir el autoservicio web autenticado para que cada usuario gestione sus
memorias y credenciales, consulte estadísticas propias y conserve el
aislamiento impuesto por PostgreSQL.
## Requirements
### Requirement: Identidad derivada exclusivamente de la sesión
Todas las operaciones de esta capacidad MUST requerir una sesión web válida y MUST derivar de ella el usuario. La API MUST NOT aceptar el usuario, propietario o inquilino como dato controlable por el cliente.

#### Scenario: Sesión ausente o inválida
- **WHEN** una petición llega sin sesión válida
- **THEN** el sistema la rechaza sin ejecutar lógica de memorias

#### Scenario: Intento de indicar otro usuario
- **WHEN** una petición incluye un identificador de usuario en su cuerpo, ruta o parámetros
- **THEN** el sistema lo ignora y opera sobre el usuario de la sesión

#### Scenario: Aislamiento en base de datos
- **WHEN** se ejecuta cualquier lectura o escritura de memorias
- **THEN** se realiza con el contexto de usuario fijado, de modo que las políticas de la base de datos siguen aplicándose

### Requirement: Enumeración de memorias propias
El sistema MUST permitir enumerar las memorias activas del usuario con filtros por ámbito, proyecto y categoría, MUST paginar los resultados y MUST informar del total disponible.

#### Scenario: Enumeración sin filtros
- **WHEN** se solicitan las memorias sin filtros
- **THEN** el sistema devuelve una página de memorias activas junto al total, el tamaño de página y el desplazamiento aplicados

#### Scenario: Filtro por proyecto
- **WHEN** se solicitan las memorias de un proyecto concreto
- **THEN** el sistema devuelve las de ese proyecto según las reglas de visibilidad vigentes

#### Scenario: Página mayor que el máximo permitido
- **WHEN** se solicita un tamaño de página superior al máximo del dominio
- **THEN** el sistema aplica el máximo permitido y comunica el valor efectivo

#### Scenario: Memorias retiradas
- **WHEN** existen memorias retiradas o sustituidas
- **THEN** no aparecen en la enumeración de memorias activas

### Requirement: Consulta de una memoria concreta
El sistema MUST permitir obtener una memoria propia por su identificador y MUST responder de forma
idéntica ante un identificador inexistente y uno perteneciente a otro usuario.

#### Scenario: Memoria propia
- **WHEN** se solicita una memoria del usuario de la sesión
- **THEN** el sistema devuelve su contenido, categoría, ámbito, proyecto, importancia, metadata, fecha de creación y, cuando existen, sus señales de reconfirmación y de uso

#### Scenario: Identificador ajeno o inexistente
- **WHEN** se solicita una memoria de otro usuario o un identificador que no existe
- **THEN** el sistema responde de la misma manera en ambos casos, sin revelar cuál es

### Requirement: Búsqueda híbrida de memorias propias
El sistema MUST permitir buscar entre las memorias propias combinando relevancia semántica y textual, y MUST indicar cuándo el resultado proviene únicamente del ranking textual.

#### Scenario: Búsqueda con embeddings disponibles
- **WHEN** se busca una consulta y el servicio de embeddings responde
- **THEN** el sistema devuelve resultados ordenados por la fusión de ambos rankings

#### Scenario: Búsqueda degradada
- **WHEN** el servicio de embeddings no está disponible
- **THEN** el sistema devuelve resultados textuales e indica que la búsqueda está degradada

#### Scenario: Sin coincidencias
- **WHEN** ninguna memoria coincide con la consulta
- **THEN** el sistema devuelve un resultado vacío y no un error

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

### Requirement: Corrección de atributos sin cambiar la identidad
El sistema MUST permitir modificar importancia, categoría y metadata de una memoria propia conservando su identificador, y MUST NOT permitir modificar su ámbito ni su proyecto.

#### Scenario: Cambio de importancia
- **WHEN** se corrige la importancia de una memoria
- **THEN** la memoria conserva su identificador y su contenido

#### Scenario: Intento de cambiar el ámbito
- **WHEN** se intenta modificar el ámbito o el proyecto
- **THEN** el sistema rechaza la operación

#### Scenario: Sin servicio de embeddings
- **WHEN** el servicio de embeddings no está disponible
- **THEN** la corrección de atributos se completa igualmente

### Requirement: Sustitución explícita de contenido
El sistema MUST ofrecer la sustitución de contenido como operación distinta de la corrección de atributos. La sustitución MUST retirar la memoria original, MUST crear una nueva con identificador propio enlazada a la anterior, y MUST identificar ambas en su respuesta.

#### Scenario: Sustituir el contenido
- **WHEN** se sustituye el contenido de una memoria
- **THEN** el sistema retira la original, crea una nueva enlazada a ella y devuelve ambos identificadores

#### Scenario: La corrección de atributos no sustituye
- **WHEN** se corrigen únicamente atributos
- **THEN** no se retira ninguna memoria ni se crea ninguna nueva

#### Scenario: Sustitución que colisiona con otra memoria activa
- **WHEN** el contenido nuevo coincide con el de otra memoria activa
- **THEN** el sistema rechaza la sustitución explicando el conflicto

#### Scenario: Sin servicio de embeddings
- **WHEN** el servicio de embeddings no está disponible
- **THEN** el sistema rechaza la sustitución indicando que la causa es la falta de ese servicio

### Requirement: Consulta de la cadena de sustituciones
El sistema MUST permitir consultar las memorias que una memoria dada ha ido sustituyendo, en orden temporal.

#### Scenario: Memoria con historia
- **WHEN** se consulta una memoria que sustituyó a otras
- **THEN** el sistema devuelve las anteriores con su contenido y la fecha en que fueron retiradas

#### Scenario: Memoria sin historia
- **WHEN** se consulta una memoria que nunca sustituyó a ninguna
- **THEN** el sistema devuelve una cadena vacía

#### Scenario: Cadena de otro usuario
- **WHEN** se consulta la cadena de una memoria ajena
- **THEN** el sistema responde igual que ante un identificador inexistente

### Requirement: Retirada de memorias propias
El sistema MUST permitir retirar una memoria propia y MUST dejar de incluirla en enumeraciones y búsquedas.

#### Scenario: Retirar una memoria
- **WHEN** se retira una memoria propia
- **THEN** deja de aparecer entre las activas

#### Scenario: Retirar algo inexistente o ajeno
- **WHEN** se intenta retirar una memoria ajena o inexistente
- **THEN** el sistema responde igual en ambos casos y no retira nada

### Requirement: Gestión de las API keys propias
El sistema MUST permitir a cada usuario enumerar, emitir y revocar sus propias API keys, y MUST NOT permitir operar sobre las de otros usuarios.

#### Scenario: Enumerar keys propias
- **WHEN** el usuario consulta sus keys
- **THEN** el sistema devuelve su etiqueta, fecha de creación, último uso y estado, sin ningún secreto

#### Scenario: Revocar una key propia
- **WHEN** el usuario revoca una de sus keys
- **THEN** deja de autenticar llamadas de herramientas MCP

#### Scenario: Operar sobre una key ajena
- **WHEN** el usuario intenta revocar una key que no le pertenece
- **THEN** el sistema responde igual que ante una key inexistente

### Requirement: Emisión de API key con confirmación de contraseña
El sistema MUST exigir la contraseña del usuario para emitir una API key nueva, MUST devolver el secreto una única vez y MUST NOT ofrecer ninguna forma de recuperarlo después. Revocar MUST NOT exigir la contraseña.

#### Scenario: Emisión con contraseña correcta
- **WHEN** el usuario emite una key y aporta su contraseña correcta
- **THEN** el sistema crea la key y devuelve el secreto una sola vez

#### Scenario: Emisión sin contraseña o con contraseña incorrecta
- **WHEN** la contraseña falta o no coincide
- **THEN** el sistema no crea ninguna key

#### Scenario: Recuperar el secreto más tarde
- **WHEN** se consulta una key ya creada
- **THEN** el sistema no devuelve su secreto por ningún medio

#### Scenario: Revocación
- **WHEN** el usuario revoca una key
- **THEN** el sistema no le pide la contraseña

### Requirement: Estadísticas de las memorias propias
El sistema MUST ofrecer estadísticas derivadas de las memorias del propio usuario, incluyendo distribución por categoría, ámbito, proyecto e importancia, evolución temporal, volumen almacenado y proporción entre memorias sustituidas y retiradas. Las estadísticas MUST NOT incluir memorias de otros usuarios.

#### Scenario: Usuario con memorias
- **WHEN** el usuario consulta sus estadísticas
- **THEN** el sistema devuelve los agregados de sus propias memorias

#### Scenario: Usuario sin memorias
- **WHEN** el usuario no tiene ninguna memoria
- **THEN** el sistema devuelve agregados en cero en lugar de un error

#### Scenario: Sin servicio de embeddings
- **WHEN** el servicio de embeddings no está disponible
- **THEN** las estadísticas se calculan igualmente

#### Scenario: Sustituidas frente a retiradas
- **WHEN** existen memorias retiradas por el usuario y memorias sustituidas por otras
- **THEN** el sistema las contabiliza por separado

### Requirement: Estado del servicio de embeddings diferenciado
El sistema MUST distinguir la indisponibilidad del servicio de embeddings de cualquier otro fallo, de modo que el cliente pueda deshabilitar únicamente las operaciones afectadas.

#### Scenario: Operación que requiere embeddings
- **WHEN** falla una creación o sustitución por falta del servicio de embeddings
- **THEN** el sistema lo indica de forma distinguible de un error genérico

#### Scenario: Operaciones no afectadas
- **WHEN** el servicio de embeddings no está disponible
- **THEN** enumerar, leer, corregir atributos, retirar y consultar estadísticas siguen funcionando

### Requirement: Contrato de la API publicado
El sistema MUST publicar la descripción de la API web como artefacto versionado en el repositorio y MUST detectar cuando el artefacto deja de corresponderse con la implementación.

#### Scenario: Contrato al día
- **WHEN** se comprueba el contrato publicado frente a la implementación
- **THEN** la comprobación pasa

#### Scenario: API modificada sin regenerar el contrato
- **WHEN** cambia la API y no se actualiza el artefacto
- **THEN** la comprobación falla indicando la divergencia

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

