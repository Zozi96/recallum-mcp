## ADDED Requirements

### Requirement: Matriz mínima de adherencia observada
El proyecto MUST documentar y poder ejecutar una matriz mínima de benchmark observado que cubra al menos los clientes soportados con política de checkpoints vigente, con repeticiones suficientes para distinguir un acierto aislado de una tasa. Las omisiones e incompletas MUST permanecer visibles en el informe y MUST NOT rellenarse con fixtures equivalentes.

#### Scenario: Matriz por cliente
- **WHEN** el operador ejecuta la matriz mínima configurada
- **THEN** el informe presenta resultados separados por cliente y política para cada escenario de la matriz

#### Scenario: Evidencia insuficiente
- **WHEN** un cliente de la matriz no está configurado o todas sus ejecuciones quedan incompletas
- **THEN** el informe marca ese hueco sin sustituirlo por trazas fixture

### Requirement: Runbook operativo del benchmark
El proyecto MUST proporcionar un runbook que indique comando(s) de lanzamiento, variables necesarias, interpretación de omitido/incompleto, y qué artefactos versionar. El runbook MUST NOT pedir persistir prompts, consultas, razonamiento, credenciales ni contenido de memorias de producción.

#### Scenario: Operador sigue el runbook
- **WHEN** un operador configura un cliente soportado según el runbook y lanza el benchmark contra un escenario sintético
- **THEN** obtiene una traza observada acotada compatible con el evaluador de flujo

#### Scenario: Sin secretos en el dataset
- **WHEN** el runbook describe qué guardar tras una corrida
- **THEN** enumera sólo procedencia acotada y eventos del evaluador, y prohíbe contenido de usuario y credenciales
