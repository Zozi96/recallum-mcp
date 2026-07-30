# MCP Agent Integration

## Purpose

Definir la integración MCP autenticada y operable para clientes locales y remotos.
## Requirements
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
El sistema MUST publicar exactamente las capacidades de guardado individual y por lotes,
recuperación, contexto con foco opcional, enumeración, corrección y borrado mediante las
herramientas `remember`, `remember_batch`, `recall`, `context`, `list_memories`, `update` y
`forget`.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia las siete herramientas con esquemas de entrada y salida validados

#### Scenario: Contexto con foco
- **WHEN** un cliente inspecciona el esquema de `context`
- **THEN** el esquema acepta un foco de tarea opcional además del proyecto y los límites de presupuesto

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

