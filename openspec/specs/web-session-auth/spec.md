# Web Session Authentication

## Purpose

Definir autenticación web mediante contraseñas y sesiones renovables, aislada de las credenciales MCP.

## Requirements

### Requirement: Separación entre credencial web y credencial de agente
El sistema MUST tratar la sesión web y la API key como credenciales distintas. Una sesión web MUST NOT autorizar llamadas a herramientas MCP, y una API key MUST NOT autorizar peticiones a la API web.

#### Scenario: Sesión web contra el endpoint MCP
- **WHEN** una llamada a una herramienta MCP presenta únicamente una sesión web válida
- **THEN** el sistema rechaza la llamada sin ejecutar lógica de memorias

#### Scenario: API key contra la API web
- **WHEN** una petición a la API web presenta únicamente una API key válida
- **THEN** el sistema la trata como no autenticada

#### Scenario: Revocación independiente
- **WHEN** se revoca una API key de un usuario
- **THEN** sus sesiones web siguen siendo válidas, y viceversa

### Requirement: Acceso web condicionado a contraseña asignada
El sistema MUST permitir que un usuario exista sin credencial de acceso web. Un usuario sin contraseña asignada MUST conservar el acceso mediante API keys y MUST NOT poder iniciar sesión en la web.

#### Scenario: Usuario existente sin contraseña
- **WHEN** un usuario creado antes de esta capacidad intenta iniciar sesión
- **THEN** el sistema rechaza el intento y sus API keys siguen funcionando sin cambios

#### Scenario: Contraseña asignada posteriormente
- **WHEN** se asigna una contraseña a un usuario existente
- **THEN** ese usuario puede iniciar sesión conservando su identidad, sus memorias y sus API keys

### Requirement: Inicio de sesión con credenciales verificadas
El sistema MUST verificar correo y contraseña antes de emitir una sesión, MUST almacenar la contraseña únicamente mediante una función de derivación de clave resistente a fuerza bruta, MUST NOT revelar si el fallo se debe al correo o a la contraseña y MUST aplicar presupuestos configurables por origen y por combinación origen-cuenta sin bloquear globalmente una cuenta.

#### Scenario: Credenciales válidas
- **WHEN** se envía un correo con contraseña asignada y la contraseña correcta dentro del presupuesto permitido
- **THEN** el sistema establece una sesión y devuelve la identidad autenticada

#### Scenario: Contraseña incorrecta o correo desconocido
- **WHEN** la contraseña no coincide o el correo no existe
- **THEN** el sistema rechaza el intento con una respuesta y un trabajo de verificación indistinguibles entre ambos casos

#### Scenario: Almacenamiento de la contraseña
- **WHEN** se inspecciona el registro del usuario
- **THEN** la contraseña no aparece en claro ni como resumen de una función de hash rápida de propósito general

#### Scenario: Presupuesto de login agotado
- **WHEN** un origen o una combinación origen-cuenta supera el número configurado de intentos fallidos
- **THEN** el sistema responde `429` con `Retry-After` sin verificar otra contraseña durante esa ventana y sin indicar cuál presupuesto se agotó

### Requirement: Sesión renovable con doble caducidad
Cada sesión MUST tener una ventana de inactividad que se renueva con el uso y un vencimiento absoluto que no se extiende nunca. El sistema MUST rechazar toda sesión que haya superado cualquiera de los dos.

#### Scenario: Uso continuado
- **WHEN** el usuario realiza peticiones autenticadas dentro de la ventana de inactividad
- **THEN** la sesión sigue siendo válida sin pedir credenciales de nuevo

#### Scenario: Inactividad prolongada
- **WHEN** transcurre la ventana de inactividad completa sin peticiones
- **THEN** el sistema rechaza la sesión y exige iniciar sesión de nuevo

#### Scenario: Vencimiento absoluto alcanzado
- **WHEN** una sesión en uso continuo alcanza su vencimiento absoluto
- **THEN** el sistema la rechaza aunque la actividad haya sido constante

### Requirement: Rotación del testigo de sesión
El sistema MUST sustituir el testigo de sesión por uno nuevo antes de que expire su ventana de inactividad y MUST NOT realizar una escritura de rotación en cada petición autenticada.

#### Scenario: Renovación durante el uso
- **WHEN** una petición autenticada llega tras haberse consumido buena parte de la ventana de inactividad
- **THEN** el sistema emite un testigo nuevo y mantiene la identidad de la sesión

#### Scenario: Peticiones frecuentes
- **WHEN** se realizan muchas peticiones autenticadas en un intervalo corto
- **THEN** el sistema no rota el testigo en cada una de ellas

### Requirement: Detección de reutilización de un testigo rotado
El sistema MUST reconocer la presentación de un testigo ya sustituido como indicio de copia y MUST invalidar la cadena de sesión completa a la que pertenece, no sólo el testigo presentado.

#### Scenario: Testigo antiguo reaparece
- **WHEN** se presenta un testigo que ya fue sustituido por rotación
- **THEN** el sistema rechaza la petición e invalida también el testigo vigente de esa cadena

#### Scenario: Consecuencia para el portador legítimo
- **WHEN** una cadena queda invalidada por reutilización
- **THEN** todos sus portadores deben iniciar sesión de nuevo

### Requirement: Cierre de sesión explícito
El sistema MUST permitir cerrar la sesión en curso, MUST invalidarla en el servidor y MUST NOT limitarse a retirarla del cliente.

#### Scenario: Cierre de sesión
- **WHEN** un usuario autenticado cierra la sesión
- **THEN** el sistema la invalida y retira la credencial del cliente

#### Scenario: Reutilización tras el cierre
- **WHEN** se presenta el testigo de una sesión ya cerrada
- **THEN** el sistema rechaza la petición

### Requirement: Consulta de la identidad autenticada
El sistema MUST ofrecer una forma de conocer la identidad de la sesión en curso, incluyendo si posee privilegios de administración, y MUST NOT incluir secretos en la respuesta.

#### Scenario: Sesión válida
- **WHEN** se consulta la identidad con una sesión válida
- **THEN** el sistema devuelve el identificador y el correo del usuario junto con su condición de administrador

#### Scenario: Sin sesión
- **WHEN** se consulta la identidad sin sesión válida
- **THEN** el sistema responde como no autenticado y no revela si el correo existe

### Requirement: Confinamiento de la credencial de sesión en el cliente
La credencial de sesión MUST NOT ser accesible desde JavaScript, MUST viajar únicamente por conexiones cifradas, MUST estar restringida al host de la API y MUST NOT acompañar a peticiones dirigidas al endpoint MCP.

#### Scenario: Acceso desde el navegador
- **WHEN** una página intenta leer la credencial de sesión mediante JavaScript
- **THEN** no puede obtenerla

#### Scenario: Petición al endpoint MCP desde el navegador
- **WHEN** el navegador emite una petición hacia el endpoint MCP
- **THEN** la credencial de sesión no se adjunta

#### Scenario: Otros servicios del mismo dominio padre
- **WHEN** el navegador emite una petición a otro subdominio del dominio compartido
- **THEN** la credencial de sesión no se adjunta

### Requirement: Origen web autorizado
El sistema MUST aceptar peticiones autenticadas con credenciales desde el origen declarado del sitio de administración, MUST rechazar orígenes no declarados y MUST NOT extender esa autorización al endpoint MCP.

#### Scenario: Origen del sitio de administración
- **WHEN** el sitio de administración realiza una petición autenticada a la API web
- **THEN** el sistema la acepta y permite el envío de credenciales

#### Scenario: Origen no declarado
- **WHEN** una página de otro origen intenta llamar a la API web
- **THEN** el navegador impide el acceso a la respuesta

#### Scenario: Endpoint MCP
- **WHEN** una página web intenta llamar al endpoint MCP
- **THEN** el sistema no anuncia permiso de acceso entre orígenes para esa ruta

### Requirement: Rol de administrador sin acceso a memorias ajenas
El sistema MUST registrar qué usuarios son administradores y MUST NOT conceder a esa condición ninguna capacidad de leer memorias de otros usuarios.

#### Scenario: Usuario ordinario
- **WHEN** se crea un usuario sin indicación explícita
- **THEN** no es administrador

#### Scenario: Administrador consultando memorias
- **WHEN** un administrador intenta obtener memorias de otro usuario
- **THEN** el sistema no devuelve ninguna, con independencia de la lógica de aplicación

### Requirement: Administración de credenciales web desde el CLI
La herramienta de administración MUST permitir asignar una contraseña a un usuario existente y conceder la condición de administrador, y MUST NOT aceptar la contraseña de forma que quede registrada en el historial del intérprete de comandos.

#### Scenario: Asignar contraseña
- **WHEN** el operador asigna una contraseña a un usuario existente por su correo
- **THEN** ese usuario puede iniciar sesión en la web

#### Scenario: Conceder administración
- **WHEN** el operador concede la condición de administrador a un usuario
- **THEN** su identidad autenticada la refleja

#### Scenario: Usuario inexistente
- **WHEN** se indica un correo que no corresponde a ningún usuario
- **THEN** el comando falla indicándolo y no crea al usuario

#### Scenario: Introducción de la contraseña
- **WHEN** el operador ejecuta el comando de asignación de contraseña
- **THEN** la contraseña se solicita de forma interactiva y no se toma de un argumento de línea de comandos

### Requirement: Entradas de autenticación acotadas
El sistema MUST imponer un máximo de bytes al cuerpo de autenticación y un máximo de longitud a cada contraseña antes de ejecutar la función de derivación.

#### Scenario: Cuerpo de login excesivo
- **WHEN** el cuerpo de login excede el límite configurado con o sin `Content-Length`
- **THEN** el sistema responde `413` antes de parsear el cuerpo completo o ejecutar Argon2

#### Scenario: Contraseña excesiva
- **WHEN** login o una confirmación sensible recibe una contraseña mayor al máximo documentado
- **THEN** el sistema rechaza la entrada como inválida sin ejecutar la verificación costosa

### Requirement: Atribución confiable del cliente
El sistema MUST usar el peer de red inmediato para atribuir límites y MUST procesar `X-Forwarded-For` sólo cuando el peer pertenece a un CIDR confiable configurado. En ese caso MUST recorrer la cadena de derecha a izquierda, omitir saltos que pertenezcan a CIDR confiables y seleccionar la primera IP no confiable; una cadena malformada MUST caer al peer inmediato.

#### Scenario: Header reenviado por peer no confiable
- **WHEN** un cliente directo envía `X-Forwarded-For` o `Forwarded`
- **THEN** el sistema ignora ese valor para rate limiting y observabilidad

#### Scenario: Petición desde Traefik permitido
- **WHEN** el peer pertenece a un CIDR de proxy permitido y envía una cadena válida de forwarding
- **THEN** el sistema deriva como cliente la primera IP no confiable al recorrer `X-Forwarded-For` de derecha a izquierda

#### Scenario: Valor falsificado antepuesto
- **WHEN** un atacante antepone una IP falsa a una cadena que Traefik completa con la IP real a su derecha
- **THEN** el sistema se detiene en la IP real no confiable y no usa el valor antepuesto

### Requirement: Respuestas web no cacheables
El sistema MUST marcar las respuestas de autenticación y todas las respuestas privadas de `/api/v1` como no almacenables por navegadores, proxies y caches compartidos.

#### Scenario: Respuesta de login o endpoint privado
- **WHEN** el servidor responde a login, logout o una ruta autenticada
- **THEN** la respuesta incluye `Cache-Control: no-store` y no habilita cache compartido
