## ADDED Requirements

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

## MODIFIED Requirements

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
