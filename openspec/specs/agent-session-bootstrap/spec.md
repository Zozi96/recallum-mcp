# agent-session-bootstrap Specification

## Purpose
Definir cómo el plugin prepara a un agente al iniciar o reanudar sesión: clave canónica de
proyecto, inyección de contexto, visibilidad de fallos del MCP y guía de delegación.
## Requirements
### Requirement: Clave canónica de proyecto robusta
El hook de sesión MUST derivar una clave de proyecto opaca y estable: a partir del remote `origin`
cuando existe, de cualquier otro remote configurado cuando `origin` falta, y de la ruta raíz del
repositorio sólo como último recurso.

#### Scenario: Repositorio con origin
- **WHEN** el repositorio tiene remote `origin`
- **THEN** la clave es `remote:` con el hash del host y ruta canónicos, sin credenciales

#### Scenario: Repositorio sin origin pero con otro remote
- **WHEN** el repositorio no tiene `origin` pero sí otro remote configurado
- **THEN** el hook usa ese remote para derivar la misma forma de clave `remote:`

#### Scenario: Repositorio sin remotes
- **WHEN** el repositorio no tiene ningún remote
- **THEN** el hook deriva una clave `local:` a partir de la ruta raíz resuelta

### Requirement: Digest de contexto opcional al iniciar sesión
Cuando la configuración opt-in del digest está presente, el hook de sesión MUST intentar obtener un
digest compacto del contexto del proyecto directamente del servidor Recallum e inyectarlo como
contexto adicional; el intento MUST ser fail-open y no exceder el presupuesto de tiempo del hook.

#### Scenario: Digest disponible
- **WHEN** las variables de configuración del digest están definidas y el servidor responde a tiempo
- **THEN** el hook inyecta el digest compacto junto con la instrucción de usar `recall` para detalle

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

