# Service Runtime Resilience

## Purpose

Definir startup transaccional, readiness acotado, topología MCP soportada y observabilidad HTTP segura del runtime.

## Requirements

### Requirement: Startup con cleanup transaccional
El sistema MUST registrar el cleanup de cada recurso antes de iniciar el siguiente componente y MUST ejecutarlo exactamente una vez, en orden inverso, ante fallo parcial, cancelación o shutdown normal.

#### Scenario: Validador de exposición falla
- **WHEN** un validador de FastMCP falla antes de iniciar telemetría
- **THEN** el engine y los clientes ya construidos se cierran y la aplicación no acepta tráfico

#### Scenario: Inicio de telemetría falla
- **WHEN** telemetría falla durante startup
- **THEN** el contenedor se cierra sin intentar detener un componente que nunca terminó de iniciar

#### Scenario: Shutdown normal
- **WHEN** Granian solicita apagar una aplicación iniciada correctamente
- **THEN** telemetría se drena antes de cerrar clientes y engine, sin doble cierre

### Requirement: Readiness concurrente y acotado
El sistema MUST comprobar PostgreSQL y embeddings concurrentemente dentro de timeouts por dependencia y un presupuesto total configurables. `/readyz` MUST devolver un estado estable sin detalles internos y `/healthz` MUST permanecer independiente de esas dependencias.

#### Scenario: Dependencias disponibles
- **WHEN** ambas dependencias responden dentro del presupuesto
- **THEN** `/readyz` responde `200` con ambas comprobaciones en estado `ok`

#### Scenario: Dependencia lenta o caída
- **WHEN** una dependencia lanza una excepción o excede su timeout
- **THEN** `/readyz` responde `503` dentro del presupuesto total e identifica sólo la dependencia como no disponible

#### Scenario: Dependencias caídas durante liveness
- **WHEN** PostgreSQL y embeddings no están disponibles pero el proceso ASGI responde
- **THEN** `/healthz` responde que el proceso está vivo

### Requirement: Topología MCP soportada explícita
El sistema MUST ejecutar un worker y una réplica mientras el transporte MCP conserve sesiones en memoria, y MUST impedir configurar múltiples workers como si estuvieran soportados.

#### Scenario: Configuración stateful soportada
- **WHEN** el runtime se inicia en modo stateful con un worker
- **THEN** startup continúa y el modo queda documentado en la configuración operativa

#### Scenario: Múltiples workers stateful
- **WHEN** la configuración solicita más de un worker sin una estrategia stateless o de estado compartido validada
- **THEN** la configuración falla antes de aceptar tráfico con un mensaje operativo accionable

### Requirement: Observabilidad HTTP segura
El sistema MUST correlacionar cada petición con un request ID y MUST observar únicamente método, plantilla de ruta, status y latencia mediante campos de baja cardinalidad. La superficie de métricas operativas MUST estar protegida contra exposición pública accidental con el mismo rigor que los endpoints de salud y MUST NOT exponer etiquetas derivadas de query, UUID, cookie, token, correo o contenido de memoria.

#### Scenario: Petición normal
- **WHEN** una petición atraviesa FastAPI o FastMCP
- **THEN** la respuesta contiene un request ID y el evento servidor registra método, plantilla, status y latencia

#### Scenario: Datos sensibles presentes
- **WHEN** URL, headers o cuerpo contienen query, UUID, cookie, token, correo o contenido de memoria
- **THEN** logs y métricas HTTP no contienen esos valores ni crean etiquetas derivadas de ellos

#### Scenario: Request ID no confiable
- **WHEN** el cliente envía un request ID fuera del alfabeto o longitud permitidos
- **THEN** el sistema lo reemplaza por uno generado y acotado

#### Scenario: Superficie de métricas no pública
- **WHEN** un cliente no operador intenta acceder a la superficie de métricas
- **THEN** el acceso es rechazado con el mismo criterio que un endpoint protegido, sin filtrar etiquetas sensibles en la negativa
