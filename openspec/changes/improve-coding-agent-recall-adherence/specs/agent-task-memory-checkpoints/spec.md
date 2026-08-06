## ADDED Requirements

### Requirement: Benchmark con ejecuciones observadas de agentes
El proyecto MUST proporcionar un benchmark opt-in que ejecute una sesión real de un agente de código contra escenarios sintéticos deterministas y construya la traza desde llamadas de herramienta observadas y checks objetivos del resultado. La traza observada MUST NOT depender de eventos escritos manualmente ni de que el agente declare por sí mismo que aplicó una memoria.

#### Scenario: Ejecución real contra escenario sintético
- **WHEN** el operador ejecuta el benchmark con un comando de agente configurado y un escenario conocido
- **THEN** el benchmark prepara un workspace temporal, sirve el corpus sintético, observa las llamadas de memoria y produce una ejecución identificada por cliente, política, escenario y `run_id`

#### Scenario: Recuperación posterior al pivote
- **WHEN** una consulta observada contiene los identificadores sintéticos que revelan el nuevo subsistema, hipótesis o decisión
- **THEN** el benchmark clasifica el checkpoint en la fase correspondiente y registra las claves de memoria devueltas sin persistir el texto de la consulta

#### Scenario: Aplicación verificada externamente
- **WHEN** termina el proceso del agente
- **THEN** checks deterministas sobre el resultado del workspace establecen los criterios de aplicación satisfechos antes de puntuar la ejecución

#### Scenario: Cliente no configurado o ejecución fallida
- **WHEN** el comando del agente no está disponible, no puede conectarse al probe o termina sin completar el escenario
- **THEN** el benchmark informa una ejecución omitida o incompleta y no fabrica eventos ni criterios satisfechos

### Requirement: Registro observado acotado y seguro
El benchmark MUST almacenar únicamente procedencia acotada, identificadores del escenario y eventos compatibles con el evaluador de flujo. MUST NOT persistir prompts, consultas, razonamiento interno, credenciales, contenido de usuario ni contenido completo de memorias.

#### Scenario: Persistencia de una ejecución observada
- **WHEN** el benchmark escribe una traza
- **THEN** conserva sólo procedencia, cliente y versión declarados, política, escenario, `run_id`, fases, nombres de herramienta, claves retornadas, caracteres servidos, criterios objetivos y estado de finalización

#### Scenario: Consulta recibida por el probe
- **WHEN** el probe necesita inspeccionar una consulta sintética para seleccionar resultados o clasificar una fase
- **THEN** la procesa sólo en memoria y guarda exclusivamente la clasificación y las claves de memoria resultantes

#### Scenario: Workspace del benchmark
- **WHEN** finaliza o falla una ejecución
- **THEN** los datos temporales y credenciales efímeras del probe no se incorporan al dataset versionado

### Requirement: Comparación repetida por cliente y política
El evaluador MUST distinguir trazas fixture de trazas observadas, aceptar varias ejecuciones con `run_id` único para la misma combinación de cliente, política y escenario, y presentar por grupo la cobertura de ejecuciones junto con recuperación crítica, aplicación correcta, llamadas innecesarias, repetición y coste de contexto.

#### Scenario: Compatibilidad con fixtures vigentes
- **WHEN** el evaluador carga el dataset versionado existente sin metadatos de procedencia o cliente
- **THEN** lo trata como fixture compatible y conserva sus métricas actuales

#### Scenario: Repeticiones de una política
- **WHEN** existen varias ejecuciones observadas del mismo cliente, política y escenario
- **THEN** el informe incluye todas las repeticiones y muestra tasas o promedios comparables en lugar de seleccionar silenciosamente la primera

#### Scenario: Comparación entre clientes
- **WHEN** existen ejecuciones observadas de más de un cliente
- **THEN** el informe mantiene separados los resultados por cliente y política para no ocultar diferencias de adherencia

#### Scenario: Procedencia mixta
- **WHEN** un conjunto contiene fixtures escritos a mano y ejecuciones observadas
- **THEN** el informe etiqueta y separa ambas procedencias en lugar de presentarlas como evidencia equivalente
