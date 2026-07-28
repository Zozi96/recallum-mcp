## ADDED Requirements

### Requirement: Registro de la actividad de herramientas
El sistema MUST registrar cada llamada a una herramienta MCP autenticada, incluyendo la herramienta invocada, el usuario, el proyecto cuando aplique, la duración, el número de resultados devueltos y el instante de la llamada.

#### Scenario: Llamada correcta
- **WHEN** un agente autenticado invoca una herramienta y esta se completa
- **THEN** el sistema registra la actividad correspondiente

#### Scenario: Llamada fallida
- **WHEN** una herramienta falla durante su ejecución
- **THEN** el sistema registra igualmente la actividad e indica que no se completó

#### Scenario: Llamada rechazada por credencial
- **WHEN** una llamada se rechaza por credencial ausente, inválida o revocada
- **THEN** el sistema no registra actividad, porque no hay identidad verificada a la que atribuirla

### Requirement: Ausencia de contenido de usuario en el registro
El registro de actividad MUST NOT contener el texto de las consultas, el contenido de las memorias ni ningún fragmento de ellas.

#### Scenario: Recuperación registrada
- **WHEN** se registra una operación de recuperación
- **THEN** el registro incluye métricas de la operación pero no la consulta realizada

#### Scenario: Creación registrada
- **WHEN** se registra la creación de una memoria
- **THEN** el registro no incluye el contenido almacenado

#### Scenario: Inspección del registro
- **WHEN** se inspecciona el almacenamiento de actividad
- **THEN** no es posible reconstruir a partir de él ninguna memoria ni consulta

### Requirement: Registro de la degradación por embeddings
El sistema MUST registrar cuándo una recuperación se sirvió únicamente con ranking textual por indisponibilidad del servicio de embeddings.

#### Scenario: Servicio disponible
- **WHEN** una recuperación usa ranking semántico y textual
- **THEN** la actividad no se marca como degradada

#### Scenario: Servicio no disponible
- **WHEN** una recuperación se sirve sólo con ranking textual
- **THEN** la actividad se marca como degradada

### Requirement: Registro sin escritura sincrónica por llamada
El sistema MUST NOT realizar una escritura en base de datos por cada llamada de herramienta como parte de la llamada. La actividad MUST acumularse y volcarse de forma agrupada al superar un número de eventos o un intervalo de tiempo.

#### Scenario: Ráfaga de llamadas
- **WHEN** se producen muchas llamadas en un intervalo corto
- **THEN** el sistema agrupa su actividad en un número de escrituras mucho menor que el de llamadas

#### Scenario: Actividad esporádica
- **WHEN** se produce actividad aislada que no alcanza el tamaño de lote
- **THEN** el sistema la vuelca igualmente al cumplirse el intervalo

#### Scenario: Efecto en la llamada
- **WHEN** se instrumenta una llamada de herramienta
- **THEN** el registro no añade a esa llamada ninguna espera por base de datos

### Requirement: Acotación y durabilidad del registro pendiente
El sistema MUST acotar la actividad pendiente de volcar, MUST volcarla durante un cierre ordenado y MAY perderla ante una terminación abrupta.

#### Scenario: Cierre ordenado
- **WHEN** la aplicación se detiene de forma controlada
- **THEN** el sistema vuelca la actividad pendiente antes de terminar

#### Scenario: Volcado imposible
- **WHEN** el volcado no puede completarse y la actividad pendiente alcanza su límite
- **THEN** el sistema descarta la actividad más antigua y continúa atendiendo llamadas

#### Scenario: Fallo del volcado
- **WHEN** una escritura de actividad falla
- **THEN** las llamadas de herramientas siguen funcionando con normalidad

### Requirement: Consulta de la actividad propia
El sistema MUST permitir a un usuario autenticado consultar la actividad de su propia memoria, incluyendo evolución temporal, reparto por herramienta, reparto por proyecto y frecuencia de degradación. La respuesta MUST NOT incluir actividad de otros usuarios.

#### Scenario: Usuario con actividad
- **WHEN** un usuario consulta su actividad
- **THEN** el sistema devuelve los agregados de sus propias llamadas

#### Scenario: Usuario sin actividad
- **WHEN** un usuario sin llamadas registradas consulta su actividad
- **THEN** el sistema devuelve agregados en cero en lugar de un error

#### Scenario: Aislamiento
- **WHEN** dos usuarios tienen actividad registrada
- **THEN** ninguno ve en sus agregados la actividad del otro

### Requirement: Retención acotada de la actividad
El sistema MUST descartar la actividad registrada que supere un plazo de retención configurable y MUST NOT descartar actividad dentro de ese plazo.

#### Scenario: Actividad antigua
- **WHEN** existe actividad más antigua que el plazo de retención
- **THEN** el sistema la elimina

#### Scenario: Actividad reciente
- **WHEN** existe actividad dentro del plazo de retención
- **THEN** el sistema la conserva

#### Scenario: Purga en curso
- **WHEN** se ejecuta la purga
- **THEN** las llamadas de herramientas y las consultas de actividad siguen funcionando
