# MCP Agent Integration

## Purpose

Definir la integración MCP autenticada y operable para clientes locales y remotos.
## Requirements
### Requirement: Acceso MCP mediante HTTPS
El sistema MUST exponer las herramientas de memoria mediante FastMCP sobre Streamable HTTP detrás de Traefik en el endpoint canónico `/mcp/` y MUST soportar clientes en la misma máquina y clientes remotos. La ruta heredada `/mcp` MUST NOT ser el endpoint configurado de ningún cliente soportado.

#### Scenario: Conexión remota válida
- **WHEN** Codex, Claude Code o Cursor se conecta al endpoint `/mcp/` mediante HTTPS con credenciales válidas
- **THEN** el cliente puede descubrir y llamar las herramientas de Recallum sin atravesar un redirect

#### Scenario: Conexión desde el VPS
- **WHEN** un cliente local usa el mismo endpoint HTTPS `/mcp/` y credenciales válidas
- **THEN** obtiene las mismas herramientas y comportamiento que un cliente remoto

#### Scenario: Ruta heredada
- **WHEN** un cliente solicita `/mcp`
- **THEN** recibe únicamente una ubicación relativa hacia `/mcp/` y debe configurar la ruta canónica para continuar

### Requirement: Autenticación obligatoria
El sistema MUST exigir una API key en toda petición HTTP dirigida al transporte MCP, MUST invocar su política de autenticación antes de inicializar el protocolo, asignar una sesión o revelar capacidades, y MUST derivar de ella la identidad del usuario. Con el cache de identidad en cero, el sistema MUST comprobar el estado activo en cada petición y ofrecer revocación inmediata. Si un operador configura un cache mayor que cero, el sistema MUST declarar ese TTL como la demora máxima de revocación, MUST NOT extender la ventana al reutilizar la entrada y MUST NOT aceptar la key después de expirar. El sistema MUST NOT aceptar como identidad ningún selector enviado en los argumentos de herramientas o recursos.

#### Scenario: Token válido
- **WHEN** una petición MCP incluye `Authorization: Bearer` con una API key activa
- **THEN** el sistema permite inicializar, descubrir y ejecutar capacidades usando exclusivamente el usuario asociado a la key

#### Scenario: Token ausente, inválido o revocado sin cache
- **WHEN** una petición de initialize, ping, listado, lectura o llamada no incluye token o incluye una API key inválida o revocada con el cache configurado en cero
- **THEN** el sistema la rechaza en la frontera HTTP sin asignar una sesión, revelar capacidades ni ejecutar lógica de memorias

#### Scenario: Key revocada durante una sesión sin cache
- **WHEN** una API key se revoca después de inicializar una sesión MCP con el cache configurado en cero y se envía la siguiente petición con esa key
- **THEN** el sistema rechaza esa petición antes de ejecutar la operación aunque el identificador de sesión siga siendo válido

#### Scenario: Ventana de revocación opt-in
- **WHEN** un operador configura un TTL de identidad, una key ya cacheada se revoca y avanza el reloj más allá de ese TTL
- **THEN** la key puede ser aceptada sólo dentro de la ventana documentada y se rechaza en la primera petición posterior a su expiración

### Requirement: Conjunto mínimo de herramientas
El sistema MUST publicar las capacidades de guardado individual y por lotes, recuperación, contexto con foco opcional, lectura por identificador, enumeración, corrección, consolidación, vecinos temáticos, reconfirmación y borrado mediante las herramientas `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm` y `forget`. El sistema MUST NOT publicar el grafo temático completo como herramienta MCP.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia exactamente esas once herramientas con esquemas de entrada y salida validados

#### Scenario: Contexto con foco
- **WHEN** un cliente inspecciona el esquema de `context`
- **THEN** el esquema acepta un foco de tarea opcional además del proyecto y los límites de presupuesto

#### Scenario: Vecinos de una semilla
- **WHEN** un cliente autenticado llama `related_memories` con el identificador de una memoria activa propia
- **THEN** recibe sólo vecinos temáticos de esa semilla (identificador, contenido, categoría, ámbito, proyecto y similitud), sin embeddings ni el grafo completo

#### Scenario: Semilla desconocida o ajena
- **WHEN** un cliente llama `related_memories` con un identificador desconocido, ajeno o retirado
- **THEN** recibe una lista vacía de vecinos sin revelar si el identificador existe para otro usuario

#### Scenario: Reconfirmación por identificador
- **WHEN** un cliente autenticado llama `reconfirm` con el identificador de una memoria activa propia
- **THEN** el sistema estampa la fecha de reconfirmación y devuelve la memoria actualizada con `reconfirmed=true`

#### Scenario: Reconfirmación de identificador desconocido o ajeno
- **WHEN** un cliente llama `reconfirm` con un identificador desconocido, ajeno o retirado
- **THEN** la respuesta indica `reconfirmed=false` sin revelar si pertenece a otro usuario

### Requirement: Prompts MCP del ciclo de memoria
El sistema MUST publicar exactamente los prompts `session-start`, `capture-scan` y `stale-review`. El sistema MUST NOT publicar ningún otro prompt. Ningún prompt MUST aceptar un selector de usuario.

#### Scenario: Descubrimiento de prompts
- **WHEN** un cliente autenticado lista los prompts MCP
- **THEN** aparecen únicamente `session-start`, `capture-scan` y `stale-review`

#### Scenario: Prompt no allowlisteado
- **WHEN** el servidor registra un prompt con un nombre distinto de esos tres
- **THEN** la validación de arranque falla antes de servir tráfico

#### Scenario: session-start
- **WHEN** un cliente obtiene el prompt `session-start`
- **THEN** la guía indica llamar `context` con proyecto y, cuando la tarea se conoce, foco

#### Scenario: capture-scan
- **WHEN** un cliente obtiene el prompt `capture-scan`
- **THEN** la guía indica una captura final atómica en inglés vía `remember_batch`, sin secretos ni recapitulaciones

#### Scenario: stale-review
- **WHEN** un cliente obtiene el prompt `stale-review`
- **THEN** la guía indica enumerar la cola `list_memories(stale=true)` y resolver con `get_memory`, `reconfirm`, `update`, `forget` o `merge_memories`

### Requirement: Identidad no controlable por el agente
Las herramientas MCP MUST NOT aceptar `user_id`, owner o tenant como argumentos controlables por el cliente.

#### Scenario: Inspeccionar esquemas MCP
- **WHEN** un cliente obtiene los esquemas de las herramientas
- **THEN** ningún esquema contiene un campo que permita seleccionar otro usuario

### Requirement: Estado operativo
FastAPI MUST exponer endpoints separados de liveness y readiness sin revelar secretos ni memorias.

#### Scenario: Servicio vivo
- **WHEN** el proceso web está ejecutándose
- **THEN** el endpoint de liveness responde correctamente sin depender de PostgreSQL u Ollama

#### Scenario: Dependencia no disponible
- **WHEN** PostgreSQL u Ollama no están disponibles
- **THEN** readiness indica que el servicio no está listo y no incluye credenciales ni detalles sensibles

#### Scenario: Esquema o rol PostgreSQL inseguro
- **WHEN** faltan las tablas requeridas o el rol de aplicación es superusuario, tiene `BYPASSRLS` o no posee las tablas
- **THEN** readiness indica que el servicio no está listo sin revelar detalles sensibles

### Requirement: Autenticación de recursos MCP
Toda lectura o listado de recursos MCP MUST exigir la misma autenticación por API key Bearer que las herramientas y MUST derivar de ella la identidad del usuario. El sistema MUST NOT exponer recursos legibles sin credenciales válidas.

#### Scenario: Recurso con token válido
- **WHEN** un cliente autenticado lee un recurso de perfil publicado
- **THEN** el sistema devuelve el perfil del usuario asociado a la API key

#### Scenario: Recurso sin token
- **WHEN** un cliente sin token o con token inválido intenta listar o leer recursos
- **THEN** el sistema rechaza la operación sin devolver contenido de memorias ni del perfil

### Requirement: Recurso de perfil de memoria
El sistema MUST publicar un recurso MCP de sólo lectura para el perfil materializado del usuario autenticado, con variante global y con proyecto opcional, y MUST NOT añadir herramientas de escritura ni una herramienta dedicada de lectura de perfil mientras el recurso esté disponible.

#### Scenario: Descubrimiento del recurso
- **WHEN** un cliente autenticado lista los recursos MCP
- **THEN** aparece el recurso de perfil de Recallum

#### Scenario: Lectura de perfil global
- **WHEN** un cliente autenticado lee el recurso de perfil sin proyecto
- **THEN** recibe el perfil global materializado de su usuario (slices, procedencia y disponibilidad)

#### Scenario: Lectura de perfil de proyecto
- **WHEN** un cliente autenticado lee el recurso de perfil para un proyecto concreto
- **THEN** recibe el perfil materializado de esa clave de proyecto para su usuario

#### Scenario: Sin selectores de usuario en el recurso
- **WHEN** se inspecciona el URI o los parámetros del recurso de perfil
- **THEN** no existe un parámetro que permita seleccionar el perfil de otro usuario

### Requirement: Contexto MCP incluye perfil
La herramienta `context` MUST devolver el bloque de perfil materializado y sus metadatos según la capacidad de recuperación, sin cambiar el nombre de la herramienta ni añadir herramientas nuevas para obtener el perfil.

#### Scenario: Respuesta de context con perfil
- **WHEN** un cliente autenticado llama la herramienta `context`
- **THEN** el resultado incluye el campo de perfil con disponibilidad e ítems o la marca de no disponible

### Requirement: Confidencialidad de errores MCP
El sistema MUST devolver mensajes estables y seguros para errores esperados, MUST enmascarar el detalle de excepciones inesperadas y de infraestructura, y MUST registrar el diagnóstico completo únicamente del lado servidor sin credenciales ni payloads sensibles.

#### Scenario: Fallo inesperado con sentinel interno
- **WHEN** una herramienta lanza una excepción inesperada cuyo mensaje contiene un sentinel interno
- **THEN** la respuesta MCP indica un fallo genérico y no contiene el sentinel, URLs internas, cadenas de conexión ni stack traces

#### Scenario: Servicio de embeddings no disponible
- **WHEN** una operación MCP falla porque el servicio de embeddings no está disponible
- **THEN** el cliente recibe exactamente el mensaje público `embedding service unavailable` y el detalle técnico queda sólo en un log servidor correlacionado

#### Scenario: Error de dominio seguro
- **WHEN** una entrada infringe una regla de dominio cuyo mensaje está clasificado como seguro para cliente
- **THEN** el sistema devuelve ese error accionable sin convertirlo en un fallo interno genérico

### Requirement: Endpoint MCP canónico y protegido
El sistema MUST servir MCP directamente en `/mcp/`, MUST validar el host y el origen contra allowlists configuradas y MUST NOT construir redirects absolutos a partir de headers no confiables.

#### Scenario: Ruta canónica
- **WHEN** un cliente usa la URL HTTPS permitida con la ruta exacta `/mcp/`
- **THEN** la petición llega al transporte MCP sin redirect

#### Scenario: Ruta sin slash
- **WHEN** un cliente solicita `/mcp`
- **THEN** el sistema responde con un redirect que preserva método hacia la ubicación relativa `/mcp/` y no refleja esquema ni host de la petición

#### Scenario: Host u origen no permitido
- **WHEN** una petición MCP usa un host no permitido o un origen presente que no está en la allowlist
- **THEN** el sistema la rechaza antes de autenticar, crear una sesión o procesar contenido MCP

### Requirement: Tipos críticos consistentes en MCP
El sistema MUST aplicar tipos estrictos y los mismos rangos de dominio a los parámetros MCP cuya coerción cambiaría el significado de la operación.

#### Scenario: Booleano enviado como entero
- **WHEN** un cliente envía `true` o `false` en un parámetro entero crítico como `importance`, `limit` u `offset`
- **THEN** el sistema rechaza el payload como inválido sin ejecutar la herramienta

#### Scenario: Entero válido
- **WHEN** un cliente envía un entero dentro del rango documentado
- **THEN** FastMCP y el servicio de dominio observan exactamente ese valor

### Requirement: Límites de transporte MCP
El sistema MUST rechazar cuerpos MCP mayores al límite configurado antes de materializarlos y MUST limitar los intentos de autenticación inválidos mediante una política acotada por cliente confiable.

#### Scenario: Cuerpo MCP excesivo
- **WHEN** una petición excede el máximo de bytes configurado, incluso si usa transferencia chunked
- **THEN** el sistema responde `413` sin inicializar una sesión ni parsear el mensaje completo

#### Scenario: Presupuesto de autenticación agotado
- **WHEN** un origen supera el presupuesto configurado de credenciales MCP inválidas
- **THEN** el sistema responde `429` con `Retry-After` sin consultar repetidamente la base de datos durante la ventana indicada
