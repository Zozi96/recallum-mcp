## ADDED Requirements

### Requirement: Acceso MCP mediante HTTPS
El sistema MUST exponer las herramientas de memoria mediante FastMCP sobre Streamable HTTP detrás de Traefik y MUST soportar clientes en la misma máquina y clientes remotos.

#### Scenario: Conexión remota válida
- **WHEN** Codex o Claude Code se conecta al endpoint `/mcp` mediante HTTPS con credenciales válidas
- **THEN** el cliente puede descubrir y llamar las herramientas de Recallum

#### Scenario: Conexión desde el VPS
- **WHEN** un cliente local usa el mismo endpoint HTTPS y credenciales válidas
- **THEN** obtiene las mismas herramientas y comportamiento que un cliente remoto

### Requirement: Autenticación obligatoria
El sistema MUST exigir una API key activa en todas las llamadas de herramientas MCP y MUST derivar de ella la identidad del usuario.

#### Scenario: Token válido
- **WHEN** una llamada incluye `Authorization: Bearer` con una API key activa
- **THEN** el sistema ejecuta la herramienta usando el usuario asociado a la key

#### Scenario: Token ausente, inválido o revocado
- **WHEN** una llamada no incluye token o incluye una API key inválida o revocada
- **THEN** el sistema rechaza la llamada sin ejecutar lógica de memorias

### Requirement: Conjunto mínimo de herramientas
El sistema MUST publicar exactamente las capacidades de guardado, recuperación, contexto, enumeración y borrado mediante las herramientas `remember`, `recall`, `context`, `list_memories` y `forget`.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia las cinco herramientas con esquemas de entrada y salida validados

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
