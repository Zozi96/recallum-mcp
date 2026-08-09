## Why

La auditoría vertical de Granian, FastAPI y FastMCP confirmó dos fallos de frontera explotables —inicialización y descubrimiento MCP sin autenticación de transporte, y exposición de detalles internos en errores— además de gaps operativos que hoy no tienen contratos ni pruebas de regresión. Este cambio convierte esos hallazgos en requisitos verificables y en una ruta de entrega priorizada para que el servicio pueda endurecerse sin perder el aislamiento por usuario ni la revocación inmediata por defecto; el cache opt-in conservará una ventana máxima explícita y comprobada.

## What Changes

- Autenticar cada petición MCP en la frontera HTTP antes de asignar una sesión, inicializar el protocolo o revelar herramientas y recursos; conservar la identidad derivada del token, la revocación inmediata con el cache por defecto en cero y la ventana acotada cuando un operador habilite explícitamente el cache.
- Enmascarar fallos internos de FastMCP y de embeddings, devolver errores cliente estables y registrar el diagnóstico completo sólo del lado servidor.
- Hacer canónico el endpoint `/mcp/`, validar hosts/orígenes confiables y definir el tratamiento seguro de proxy headers y redirects bajo Traefik.
- Limitar abuso y entradas costosas en login y MCP mediante presupuestos configurables, límites de cuerpo/credenciales y respuestas `413`/`429` observables.
- Endurecer los esquemas compartidos en campos críticos para impedir coerciones divergentes entre FastAPI, FastMCP y el dominio.
- Garantizar limpieza ante fallos parciales de startup, readiness concurrente y acotado, y un contrato explícito de workers/réplicas compatible con sesiones MCP.
- Añadir telemetría HTTP de baja cardinalidad y sin secretos, respuestas privadas no cacheables y una migración de búsqueda que evite contenido sensible en query strings.
- Publicar autenticación y respuestas de error reales en OpenAPI y mantener el snapshot como contrato de entrega.
- **BREAKING**: acotar los listados y volúmenes administrativos mediante paginación; reemplazar agregaciones N+1 por consultas set-based y añadir pruebas de presupuesto de consultas. La UI administrada migrará en el mismo release.
- Acotar la compatibilidad de FastMCP, encapsular usos de API privada y establecer CI con pruebas unitarias, PostgreSQL, proxy y un recorrido vertical Granian → FastAPI → FastMCP → PostgreSQL.
- Excluir `deploy/dokploy-compose.yml`: es una alternativa no utilizada, no forma parte del camino operativo soportado y su defecto conocido no es un P0 ni un bloqueo de este cambio.

## Capabilities

### New Capabilities

- `service-runtime-resilience`: startup transaccional, readiness acotado, contrato de escalado y observabilidad HTTP segura del runtime ASGI.
- `delivery-verification`: política de compatibilidad de dependencias y gates CI que prueban las fronteras FastMCP/FastAPI en sus entornos relevantes.

### Modified Capabilities

- `mcp-agent-integration`: la autenticación cubrirá el transporte completo, los errores serán seguros y el endpoint remoto validará ruta, host y origen antes de crear sesiones.
- `web-session-auth`: el login y las sesiones incorporarán límites de abuso, de cuerpo y de credenciales, además de semántica explícita de no-cache.
- `web-self-service-api`: los tipos críticos, la búsqueda privada, la seguridad OpenAPI y las respuestas operativas quedarán alineados con el dominio.
- `web-admin-console`: listados y agregados serán paginados, acotados y ejecutados con un presupuesto constante de consultas.

## Impact

- Código: `recallum/mcp/`, `recallum/auth/`, `recallum/web/`, `recallum/app.py`, `recallum/container.py` y configuración del servidor Granian.
- Contratos: transporte Streamable HTTP MCP, endpoints web bajo `/api/v1`, snapshot `openapi/web-v1.json`, readiness y métricas/logs operativos.
- Dependencias y entrega: restricción compatible de FastMCP, adaptador de verificación de token, configuración de proxy confiable y workflows CI con PostgreSQL real.
- Pruebas: unitarias de fronteras, integración con PostgreSQL, proceso real Granian, proxy/redirect, startup fallido, revocación, aislamiento, límites y presupuestos de consultas.
- Fuera de alcance: reparar o promover `deploy/dokploy-compose.yml`, cambiar la semántica del dominio de memorias, introducir estado de sesión distribuido o habilitar escalado horizontal antes de validarlo.
