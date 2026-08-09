## MODIFIED Requirements

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

## ADDED Requirements

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
