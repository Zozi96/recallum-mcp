# Agent Task Memory Checkpoints

## Purpose

Definir cuándo y cómo un agente recupera memoria enfocada durante una tarea, verifica su vigencia y evalúa el coste y la utilidad de los checkpoints.

## Requirements

### Requirement: Checkpoint por cambio material de la tarea
La skill `recallum-memory` MUST instruir al agente a mantener conceptualmente una clave de recuperación formada por el proyecto, el objetivo activo y el subsistema, hipótesis o decisión actual, y MUST solicitar memoria adicional sólo cuando esa clave cambie materialmente y el contexto durable pueda afectar la siguiente acción.

#### Scenario: Aparece un subsistema nuevo
- **WHEN** la investigación desplaza el trabajo hacia un subsistema que no estaba representado en el foco inicial
- **THEN** el agente ejecuta un checkpoint de recuperación antes de tomar una decisión dependiente del nuevo subsistema

#### Scenario: Cambia la hipótesis causal
- **WHEN** la evidencia invalida la hipótesis activa y establece otra causa plausible
- **THEN** el agente recupera memoria usando la nueva hipótesis y los identificadores descubiertos como foco

#### Scenario: Decisión sensible con posible contexto histórico
- **WHEN** el agente está por tomar una decisión de seguridad, datos, compatibilidad, despliegue o interfaz pública y podrían existir restricciones o decisiones previas no cargadas
- **THEN** el agente ejecuta un checkpoint enfocado antes de cerrar la decisión

#### Scenario: La tarea conserva la misma clave
- **WHEN** continúan sin cambio material el proyecto, objetivo y superficie activa
- **THEN** el agente no ejecuta recuperación adicional únicamente por el paso del tiempo o la cantidad de herramientas utilizadas

### Requirement: Recuperación enfocada y acotada
En un checkpoint, la skill MUST instruir al agente a llamar `recall` con el proyecto canónico, una consulta en inglés que describa el delta de la tarea y conserve identificadores verbatim, y `limit=3`; el agente MUST usar filtros de ámbito o categoría sólo cuando la tarea los determine sin ambigüedad.

#### Scenario: Consulta del delta de tarea
- **WHEN** un fallo inicialmente atribuido a autenticación se localiza en rotación de sesiones
- **THEN** la consulta describe rotación de sesiones, la evidencia o decisión próxima y los identificadores pertinentes, en lugar de repetir el prompt original

#### Scenario: Presupuesto del checkpoint
- **WHEN** el agente ejecuta un checkpoint de recuperación
- **THEN** solicita como máximo tres resultados en esa llamada

#### Scenario: Categoría incierta
- **WHEN** el contexto relevante podría estar almacenado como decisión, restricción o hecho
- **THEN** el agente no restringe la consulta a una categoría concreta

### Requirement: Supresión de recuperaciones redundantes
La skill MUST instruir al agente a no repetir durante la misma tarea una consulta semánticamente equivalente ni solicitar de nuevo memoria que el contexto activo ya cubre de manera suficiente.

#### Scenario: Consulta equivalente ya ejecutada
- **WHEN** el agente ya consultó la misma clave de recuperación y no apareció evidencia nueva que la cambie
- **THEN** continúa con los resultados disponibles sin repetir `recall`

#### Scenario: Contexto inicial suficiente
- **WHEN** el snapshot inicial ya contiene la restricción o decisión necesaria para la siguiente acción
- **THEN** el agente aplica y verifica ese contexto sin ejecutar un checkpoint adicional

#### Scenario: Checkpoint sin resultados útiles
- **WHEN** un checkpoint no devuelve memoria aplicable
- **THEN** el agente continúa la tarea y no amplía automáticamente el límite ni encadena consultas reformuladas sin nueva evidencia

### Requirement: Reanudación y compactación conscientes del foco
La skill MUST distinguir entre el digest genérico que `SessionStart` puede inyectar en `resume|clear|compact` y un snapshot enfocado en la tarea; MUST NOT exigir otra llamada si el digest cubre el foco activo y MUST permitir una recuperación enfocada cuando no lo cubra.

#### Scenario: Digest posterior a compactación suficiente
- **WHEN** una compactación inyecta un digest que conserva las memorias necesarias para el foco activo
- **THEN** el agente no vuelve a llamar `context` ni `recall` sólo por la compactación

#### Scenario: Digest posterior a compactación insuficiente
- **WHEN** el digest inyectado no cubre el subsistema, hipótesis o decisión activos
- **THEN** el agente solicita un snapshot con foco o ejecuta un `recall` específico antes de continuar una decisión dependiente de memoria

#### Scenario: Recallum no disponible
- **WHEN** las herramientas no están disponibles después del mecanismo de descubrimiento del cliente
- **THEN** el agente informa la limitación una sola vez y continúa la tarea sin bloquearse

### Requirement: Verificación de memoria recuperada
La skill MUST exigir que toda memoria recuperada que afecte una decisión se reconcilie con las instrucciones actuales y con evidencia vigente del repositorio, y MUST tratar memoria stale, contradictoria o truncada según las reglas existentes de Recallum antes de confiar en ella.

#### Scenario: Memoria contradice el repositorio
- **WHEN** una memoria recuperada contradice la configuración o el código vigente
- **THEN** el agente trata la memoria como contexto histórico y usa la evidencia actual como autoridad

#### Scenario: Memoria aplicable y vigente
- **WHEN** una memoria recuperada coincide con las instrucciones y la evidencia actuales
- **THEN** el agente la aplica a la tarea sin volver a redescubrir su contenido

### Requirement: Evaluación reproducible del flujo
El proyecto MUST proporcionar escenarios y un evaluador separados de la evaluación de ranking para comparar el flujo vigente y la política de checkpoints sin requerir cambios al servidor ni almacenar prompts en telemetría.

#### Scenario: Escenario con pivote relevante
- **WHEN** un escenario introduce después del inicio un cambio de subsistema o hipótesis cuya decisión correcta depende de una memoria sembrada
- **THEN** la evaluación registra si el agente consultó después del pivote, recuperó la memoria esperada y la aplicó al resultado

#### Scenario: Escenario sin pivote
- **WHEN** una tarea permanece cubierta por el contexto inicial
- **THEN** la evaluación penaliza llamadas de recuperación adicionales

#### Scenario: Resultados repetidos
- **WHEN** varios checkpoints de una ejecución devuelven la misma memoria
- **THEN** la evaluación informa la proporción de exposiciones repetidas y el coste de contexto asociado

#### Scenario: Comparación entre políticas
- **WHEN** existen registros compatibles de ejecuciones con la política vigente y con checkpoints
- **THEN** el evaluador presenta por política recuperación crítica, aplicación correcta, llamadas innecesarias, repetición y coste de contexto sin reducir el resultado a la cantidad total de llamadas
