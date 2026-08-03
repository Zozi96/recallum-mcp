## MODIFIED Requirements

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
