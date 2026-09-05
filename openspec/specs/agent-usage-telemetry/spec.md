# agent-usage-telemetry Specification

## Purpose
Definir el registro privado, acotado y no bloqueante de actividad MCP autenticada,
sus agregados de autoservicio por usuario y la retención de estos datos operativos
sin almacenar consultas, contenido de memorias ni fragmentos de resultados.

## Requirements
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
El sistema MUST acotar la actividad pendiente de volcar, MUST volcarla durante un cierre ordenado, MAY perderla ante una terminación abrupta, y MUST hacer observable cuándo la pérdida por acotación ocurrió.

#### Scenario: Cierre ordenado
- **WHEN** la aplicación se detiene de forma controlada
- **THEN** el sistema vuelca la actividad pendiente antes de terminar

#### Scenario: Volcado imposible
- **WHEN** el volcado no puede completarse y la actividad pendiente alcanza su límite
- **THEN** el sistema descarta la actividad más antigua, continúa atendiendo llamadas y esa pérdida queda registrada en la superficie de métricas

#### Scenario: Fallo del volcado
- **WHEN** una escritura de actividad falla
- **THEN** las llamadas de herramientas siguen funcionando con normalidad y el fallo queda registrado en la superficie de métricas

### Requirement: Exposición operativa de métricas
El sistema MUST exponer una superficie de métricas operativas de acceso restringido a operadores (no a agentes MCP) que incluya el contador de eventos de telemetría descartados por desbordamiento, los fallos de volcado, la latencia por herramienta y la proporción de operaciones degradadas. Esa superficie MUST NOT contener contenido de memoria, datos de usuario ni etiquetas derivadas de valores sensibles.

#### Scenario: Contador de drops visible
- **WHEN** el buffer descarta eventos por desbordamiento y el operador consulta la superficie de métricas
- **THEN** el contador de eventos descartados es mayor que cero y observable

#### Scenario: Fallo de volcado visible
- **WHEN** una escritura de actividad falla y el operador consulta la superficie de métricas
- **THEN** el fallo de volcado es observable sin leer los logs

#### Scenario: Operación degradada visible
- **WHEN** recall sirve en modo `degraded_textual` o una escritura usa marcador de embedding
- **THEN** la superficie de métricas lo refleja agregado y anónimo

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
