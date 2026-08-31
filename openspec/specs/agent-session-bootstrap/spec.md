# agent-session-bootstrap Specification

## Purpose
Definir cómo el plugin prepara a un agente al iniciar o reanudar sesión: clave canónica de
proyecto, inyección de contexto, visibilidad de fallos del MCP y guía de delegación.
## Requirements
### Requirement: Clave canónica de proyecto robusta
El hook de sesión MUST derivar una clave de proyecto opaca y estable: del archivo ancla
`.recallum-project` comprometido en el repositorio cuando existe, a partir del remote `origin`
cuando existe, de cualquier otro remote configurado cuando `origin` falta, y de la ruta raíz del
repositorio sólo como último recurso. La derivación MUST existir una sola vez como código
ejecutable (`recallum_hook.py project-key`); las reglas y skills MUST apuntar a ese comando en
lugar de re-especificar el algoritmo.

#### Scenario: Ancla comprometida en el repositorio
- **WHEN** el repositorio o un directorio padre contiene `.recallum-project` con contenido `anchor:<hex>` válido
- **THEN** la clave es ese ancla, con precedencia sobre cualquier remote, y es idéntica en toda máquina que clone el repositorio

#### Scenario: Ancla malformada
- **WHEN** existe `.recallum-project` pero su contenido no cumple el formato `anchor:<hex>`
- **THEN** el hook ignora el ancla y deriva la clave por la vía normal, sin escalar a anclas de directorios padre

#### Scenario: Repositorio con origin
- **WHEN** el repositorio tiene remote `origin`
- **THEN** la clave es `remote:` con el hash del host y ruta canónicos, sin credenciales

#### Scenario: Repositorio sin origin pero con otro remote
- **WHEN** el repositorio no tiene `origin` pero sí otro remote configurado
- **THEN** el hook usa ese remote para derivar la misma forma de clave `remote:`

#### Scenario: Normalización de host insensible a mayúsculas
- **WHEN** el remote pertenece a un host con rutas insensibles a mayúsculas (p. ej. github.com, gitlab.com, bitbucket.org)
- **THEN** host y ruta se normalizan en minúsculas, de modo que `github.com/Owner/Repo` y `github.com/owner/repo` derivan la misma clave

#### Scenario: Puerto no por defecto
- **WHEN** la URL del remote usa un puerto distinto del por defecto de su esquema
- **THEN** el canonical incluye `<host>:<puerto>`, evitando colisiones entre servidores distintos en el mismo host

#### Scenario: Repositorio sin remotes
- **WHEN** el repositorio no tiene ningún remote
- **THEN** el hook deriva una clave `local:` a partir de la ruta raíz resuelta

#### Scenario: Fallo transitorio de git con caché
- **WHEN** git no responde (timeout o binario ausente) y el checkout ya derivó una clave sana antes
- **THEN** el hook reutiliza la clave cacheada en el git dir en lugar de degradar a una clave `local:` por subdirectorio

#### Scenario: Fallo transitorio de git sin caché
- **WHEN** git no responde y no existe clave cacheada
- **THEN** el hook cae a la clave por ruta como mejor estimación estable, sin cachearla, para que una ejecución sana posterior pueda derivar la clave `remote:`

### Requirement: Digest de contexto opcional al iniciar sesión
Cuando la configuración opt-in del digest está presente, el hook de sesión MUST intentar obtener un
digest compacto del contexto del proyecto directamente del servidor Recallum e inyectarlo como
contexto adicional; el intento MUST ser fail-open y no exceder el presupuesto de tiempo del hook.
Cuando la respuesta de contexto incluye un perfil materializado disponible, el digest MUST priorizar
las líneas del perfil (static antes que dynamic) frente al resto del snapshot dentro del presupuesto
de caracteres del digest.

#### Scenario: Digest disponible
- **WHEN** las variables de configuración del digest están definidas y el servidor responde a tiempo
- **THEN** el hook inyecta el digest compacto junto con la instrucción de usar `recall` para detalle

#### Scenario: Digest con perfil
- **WHEN** el digest se construye a partir de un `context` que incluye perfil disponible con ítems
- **THEN** el texto inyectado incluye primero contenido del perfil hasta el presupuesto del digest

#### Scenario: Servidor inaccesible o lento
- **WHEN** el servidor no responde, responde con error o excede el presupuesto de tiempo
- **THEN** el hook emite la instrucción estándar sin digest y la sesión continúa sin fallo

#### Scenario: Configuración ausente
- **WHEN** la configuración opt-in no está definida
- **THEN** el hook emite únicamente la instrucción estándar, sin intentar conexión alguna

### Requirement: Indisponibilidad visible de las herramientas
La guía inyectada por el hook MUST indicar al agente que, si las herramientas de Recallum no
aparecen en su lista tras buscarlas, lo comunique al usuario una única vez en lugar de continuar en
silencio.

#### Scenario: Herramientas ausentes en la sesión
- **WHEN** el agente busca las herramientas de Recallum y no existen en la sesión
- **THEN** la guía vigente le exige mencionar la indisponibilidad al usuario una sola vez y continuar

### Requirement: Guía de delegación a subagentes
La skill del plugin MUST instruir que, al delegar trabajo, el agente líder pase la clave canónica de
proyecto y las memorias relevantes en el prompt del subagente, y que los subagentes MUST NOT
escribir memorias: el líder consolida la captura al final.

#### Scenario: Delegación con contexto
- **WHEN** un agente líder delega una tarea a un subagente
- **THEN** la guía vigente le exige incluir la clave canónica y las memorias recuperadas relevantes en el prompt

#### Scenario: Captura centralizada
- **WHEN** un subagente descubre contexto reutilizable durante su tarea
- **THEN** la guía vigente indica reportarlo al líder, que decide y ejecuta la captura única

### Requirement: Ciclo de memoria visible al iniciar sesión
Cada salida de `SessionStart` MUST exponer al agente un ciclo breve y accionable de tres momentos: usar el contexto inicial o digest disponible, ejecutar un único `recall` enfocado cuando cambie materialmente el subsistema, hipótesis o decisión y la memoria durable pueda afectar la siguiente acción, y capturar al finalizar sólo contexto reutilizable verificado. La guía MUST usar los nombres de herramienta visibles para el cliente activo y MUST conservar las reglas de consulta inglesa del delta, proyecto canónico, `limit=3`, supresión cuando el contexto activo ya sea suficiente y continuidad fail-open.

#### Scenario: Inicio sin digest
- **WHEN** el hook emite la instrucción estándar porque no obtuvo un digest
- **THEN** la salida indica cargar `context` con el proyecto y foco de tarea, describe el checkpoint semántico y conserva la captura final

#### Scenario: Inicio con digest disponible
- **WHEN** el hook inyecta un digest compacto del proyecto
- **THEN** la salida evita pedir otro `context` genérico, pero conserva el checkpoint semántico para un foco nuevo y la captura final

#### Scenario: Proyecto todavía sin memorias
- **WHEN** el servidor confirma que el proyecto no tiene memorias almacenadas al iniciar
- **THEN** la salida omite la carga inicial innecesaria y mantiene la guía para recuperar ante un pivote posterior y capturar hallazgos al terminar

#### Scenario: Contexto activo suficiente
- **WHEN** el contexto inicial o digest ya contiene la memoria necesaria para la decisión siguiente
- **THEN** la guía exige aplicar y verificar ese contexto sin ejecutar un `recall` redundante

#### Scenario: Nombres de herramienta por cliente
- **WHEN** el hook se ejecuta en Codex, Claude Code o Grok Build
- **THEN** el ciclo breve nombra las herramientas según el prefijo y mecanismo de descubrimiento del cliente correspondiente

### Requirement: Guía de vecinos, reconfirmación y prompts
La skill y el recordatorio de `SessionStart` MUST enseñar el ciclo ampliado: tras un acierto útil de `recall` o `context`, la guía MUST presentar `related_memories` como paso opcional sólo cuando haga falta el entorno temático de una semilla, no en cada recuperación; ante la cola de memorias obsoletas MUST exigir un desenlace explícito (`reconfirm` / `update` / `forget` / `merge_memories`) y preferir `reconfirm` frente a volver a guardar el mismo contenido; ante `similar` MUST distinguir merge (reexpresión) de update/forget (contradicción o hecho incorrecto); y, si el cliente soporta prompts MCP, MUST nombrar `session-start`, `capture-scan` y `stale-review` como atajos del ciclo ya documentado.

#### Scenario: Vecindario opcional
- **WHEN** un `recall` o `context` devuelve una memoria útil y el agente necesita explorar el tema
- **THEN** la guía vigente menciona `related_memories` como paso opcional, no obligatorio en cada recuperación

#### Scenario: Cola obsoleta
- **WHEN** el agente verifica una memoria marcada como stale que sigue siendo cierta
- **THEN** la guía vigente indica `reconfirm` en lugar de un `remember` idéntico

#### Scenario: Cola obsoleta con desenlace
- **WHEN** el agente completa la verificación de un ítem stale
- **THEN** la guía vigente exige elegir `reconfirm`, `update`, `forget` o `merge_memories` según el resultado

#### Scenario: Similares en captura
- **WHEN** `remember` o `remember_batch` reportan similares
- **THEN** la guía vigente indica merge para reexpresiones y update/forget para contradicciones, sin auto-resolver

#### Scenario: Prompts como atajo
- **WHEN** el cliente expone prompts MCP
- **THEN** la guía vigente nombra `session-start`, `capture-scan` y `stale-review` como atajos del ciclo start → captura → revisión stale

### Requirement: Equivalencia contractual del ciclo con el benchmark
La guía de ciclo de memoria en `SessionStart` MUST permanecer alineada con los nombres de herramienta y el comportamiento fail-open que el benchmark observado asume por cliente, de modo que una mejora del runbook o de la matriz no contradiga el recordatorio inyectado.

#### Scenario: Nombre de herramienta coherente
- **WHEN** el benchmark observa un cliente concreto
- **THEN** la guía de `SessionStart` de ese cliente nombra las mismas herramientas de context/recall/captura que el escenario espera descubrir

#### Scenario: Fail-open intacto
- **WHEN** el servidor de memoria no está disponible al iniciar
- **THEN** la guía de ciclo sigue siendo emitida sin bloquear la sesión, igual que el benchmark trata omisiones sin fabricar éxito
