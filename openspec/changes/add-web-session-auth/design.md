## Context

Recallum expone hoy exactamente tres superficies HTTP: `GET /healthz`, `GET /readyz` y el mount de FastMCP en `/mcp`. Toda la administración es el CLI `recallum-admin` (`create-user`, `issue-key`, `revoke-key`, `list-keys`), que corre en proceso dentro del contenedor. No hay contraseñas, ni sesiones, ni roles, ni CORS.

El aislamiento por usuario está anclado en PostgreSQL. `SessionProvider.for_user()` fija `app.current_user_id` con `SET LOCAL` y `memories` tiene `FORCE ROW LEVEL SECURITY`; `SessionProvider.admin()` no fija nada, por lo que la política compara contra `NULL` y no selecciona ninguna memoria. `api_keys` tiene RLS sin `FORCE` y el rol de aplicación es dueño de las tablas, de ahí el bypass de dueño que necesita la búsqueda por hash previa a la autenticación. El reparto actual es estricto: `memory_repo` usa siempre `for_user()`, `user_repo` y `api_key_repo` usan siempre `admin()`.

El sitio web vivirá en `memory.zozbit.com` y la API permanece en `recallum.zozbit.com`. Ambos comparten el dominio registrable `zozbit.com`, de modo que el navegador los considera *same-site* aunque sean orígenes distintos.

El despliegue es un único usuario real (el propio operador), que será a la vez administrador y dueño de memorias.

## Goals / Non-Goals

**Goals:**

- Dar al navegador una credencial propia, revocable y de vida acotada.
- Impedir estructuralmente que una sesión web pueda invocar herramientas MCP y que una API key pueda usar la API web.
- Mantener la sesión viva durante días de uso normal sin pedir credenciales de nuevo.
- Detectar el uso de un testigo de sesión robado.
- Permitir habilitar acceso web al usuario que ya existe en producción sin recrearlo.
- Introducir el rol de administrador sin darle acceso al contenido de memorias ajenas.

**Non-Goals:**

- Registro autónomo, invitaciones, recuperación de contraseña o correo saliente.
- OAuth, SSO, organizaciones o permisos granulares.
- Segundo factor.
- Cualquier endpoint de datos (memorias, keys, estadísticas): son changes posteriores.
- Cambiar el comportamiento de las herramientas MCP.

## Decisions

### Las sesiones web viven en su propia tabla, no en `api_keys`

Reutilizar `api_keys` con una columna discriminadora sería menos código y más barato, pero pondría las dos credenciales en la misma tabla y en el mismo camino de búsqueda. Un fallo en el filtro del discriminador convertiría una cookie de navegador en una credencial MCP válida.

Con una tabla `web_sessions` separada ese fallo deja de ser improbable y pasa a ser inexpresable: `TokenAuthenticator` consulta `api_keys` y nunca `web_sessions`, y el autenticador web hace lo contrario. Es el mismo razonamiento que ya sostiene `validate_only_tools_are_exposed`, que prefiere fallar al arrancar antes que confiar en que nadie se equivoque.

### La cookie es host-only y está limitada a `/api/v1`

Las cookies se envían según la URL de destino, no según el origen de la página. Una cookie host-only emitida por `recallum.zozbit.com` acompaña a cualquier petición dirigida a ese host, incluidas las peticiones asíncronas desde `memory.zozbit.com`.

Por eso se rechaza `Domain=.zozbit.com`: ampliaría la cookie a todos los subdominios del dominio personal, entregando la sesión de Recallum a cualquier otro servicio alojado ahí. `zozbit.com` es un dominio compartido entre proyectos, así que el alcance más estrecho es el correcto.

`Path=/api/v1` es defensa en profundidad: aunque alguien lograse dirigir una petición autenticada al mount de MCP, el navegador no adjuntaría la cookie.

Atributos: `HttpOnly`, `Secure`, `SameSite=Lax`, sin `Domain`, `Path=/api/v1`.

### `SameSite=Lax` basta y aporta protección CSRF

`SameSite` se evalúa sobre el dominio registrable, no sobre el origen. `memory.zozbit.com` y `recallum.zozbit.com` comparten `zozbit.com`, así que sus peticiones asíncronas son same-site y la cookie `Lax` viaja con normalidad.

La consecuencia útil es la simétrica: una página en un dominio ajeno que intente escribir contra la API sí es cross-site, y el navegador no adjuntará la cookie a esa petición. Eso cubre CSRF sin token adicional. Se descarta `SameSite=None`, que sería obligatorio con dominios distintos y convertiría la cookie en cookie de terceros, bloqueada por Safari.

### El CORS se limita a `/api/v1` y no alcanza a `/mcp`

`CORSMiddleware` se instala sobre la aplicación completa, lo que incluiría el mount de MCP. Los agentes no son navegadores y no necesitan CORS; concedérselo sólo ampliaría superficie y permitiría que una página web intentase hablar con el endpoint de herramientas.

La política se aplica por tanto sólo a las rutas de la API web, con el origen `https://memory.zozbit.com` declarado de forma exacta. El comodín queda descartado de todas formas: el navegador lo rechaza cuando se permiten credenciales.

### Caducidad deslizante con tope absoluto y rotación por umbral

La sesión lleva dos vencimientos: una ventana de inactividad de 7 días que se desplaza con el uso, y un tope absoluto de 30 días que no se mueve nunca. La ventana da la comodidad pedida; el tope garantiza que ninguna sesión sea eterna.

Rotar el testigo en cada petición daría la máxima higiene, pero implicaría una escritura por petición. `BearerAuthMiddleware` ya resolvió este dilema para `last_used_at`, donde `LAST_USED_REFRESH_INTERVAL` cambia exactitud por no serializar el camino caliente. Se aplica el mismo criterio: la rotación ocurre sólo al cruzar la mitad de la ventana de inactividad. El usuario percibe semanas sin reautenticarse; la base de datos ve una escritura cada varios días.

### Un testigo ya rotado que reaparece implica copia

Al rotar, la fila antigua conserva el enlace a su sucesora en lugar de borrarse. Presentar un testigo rotado es imposible para el cliente legítimo, que ya recibió la cookie nueva, así que sólo ocurre si el testigo fue copiado.

La respuesta es revocar la cadena entera, no sólo el testigo presentado: si no se sabe cuál de los dos portadores es el legítimo, la única opción segura es expulsar a ambos.

### Contraseña con derivación de clave; los testigos siguen con SHA-256

`hash_token` usa SHA-256 y es correcto para API keys y testigos de sesión, porque son 32 bytes aleatorios sin espacio de búsqueda que atacar. Una contraseña humana sí lo tiene, así que necesita una función deliberadamente lenta. Se añade Argon2id, primera dependencia criptográfica del proyecto.

`password_hash` es opcional. Nulo significa "este usuario existe para MCP y no puede entrar por web", que es el estado por defecto correcto y el que conservan todos los usuarios actuales tras la migración.

### El administrador es una columna, no configuración

Una lista de correos en variables de entorno evitaría la migración y bastaría para un despliegue de un solo operador. Se descarta porque el rol acabará necesitando existir como dato en cuanto haya un segundo usuario, y retroajustarlo entonces obliga a reescribir cada punto de autorización ya escrito. La columna es barata ahora y cara después.

`is_admin` no concede acceso a memorias ajenas y no puede concederlo: RLS ya lo impide en PostgreSQL, con independencia de lo que decida la capa de aplicación.

### El acceso web se habilita desde el CLI

El usuario del operador ya existe en producción, sin contraseña y sin marca de administrador. `recallum-admin set-password` y `recallum-admin grant-admin` son la única vía de arranque, coherente con que la creación de usuarios ya sea una operación de CLI. Al no haber registro autónomo ni correo saliente, el CLI es también la única forma de recuperar el acceso.

## Risks / Trade-offs

- **La ventana de inactividad amplía el daño de un testigo robado.** Se mitiga con el tope absoluto, la rotación y la detección de reutilización, no eliminando la comodidad pedida.
- **La rotación por umbral deja una ventana en la que el testigo anterior sigue siendo válido.** Es el precio explícito de no escribir en cada petición, y es el mismo trato que el proyecto ya aceptó para `last_used_at`.
- **Argon2id consume CPU en el mismo VPS que Ollama.** El inicio de sesión es una operación rara, no un camino caliente; los parámetros se fijarán conservadores.
- **Aparece una superficie HTTP autenticada fuera de MCP.** La validación de arranque que hoy garantiza que MCP sólo expone herramientas pasa a ser aún más importante, porque deja de ser cierto que toda la aplicación esté detrás del mismo guardián.
- **La cookie depende de que ambos hosts sigan bajo `zozbit.com`.** Mover el sitio a otro dominio invalidaría este diseño y forzaría un esquema distinto. Queda anotado como supuesto, no como detalle.

## Migration Plan

1. Migración aditiva: `users.password_hash` y `users.is_admin` con valor por defecto, más la tabla `web_sessions`. Ningún usuario existente cambia de comportamiento.
2. Desplegar la API con la ruta web activa; sin contraseñas asignadas, nadie puede entrar todavía.
3. Ejecutar `set-password` y `grant-admin` sobre el usuario del operador.
4. Verificar que las herramientas MCP siguen funcionando con las API keys existentes y que la cookie no viaja a `/mcp`.

## Open Questions

- Parámetros concretos de Argon2id (memoria, iteraciones, paralelismo) frente a los recursos del VPS.
- Si la limpieza de sesiones caducadas debe ser una tarea programada o un barrido oportunista en el inicio de sesión.
- Si conviene registrar los inicios de sesión fallidos y limitar su frecuencia ya en esta change o al añadir telemetría.
