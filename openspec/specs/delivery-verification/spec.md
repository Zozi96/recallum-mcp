# Delivery Verification

## Purpose

Definir las comprobaciones de entrega, compatibilidad FastMCP y verificación en proceso real con PostgreSQL, Granian y reverse proxy.

## Requirements

### Requirement: Compatibilidad FastMCP acotada
El proyecto MUST declarar un rango de FastMCP que no cruce una versión mayor sin decisión explícita, MUST reproducir producción desde `uv.lock` y MUST concentrar cualquier acceso a APIs privadas en una única costura de compatibilidad.

#### Scenario: Instalación de producción
- **WHEN** CI o la imagen sincroniza dependencias con el lock
- **THEN** instala exactamente la versión aprobada de FastMCP dentro del rango compatible

#### Scenario: Actualización candidata compatible
- **WHEN** se evalúa la última versión permitida o un PR modifica FastMCP o `uv.lock`
- **THEN** se ejecutan los contratos de auth, middleware, exposición y lifespan antes de permitir el upgrade

#### Scenario: API privada cambia
- **WHEN** falta o cambia una operación privada usada para validar exposición
- **THEN** la costura de compatibilidad falla en startup con diagnóstico explícito y ninguna otra parte del código depende directamente de esa API

### Requirement: Gate rápido de entrega
Cada cambio MUST ejecutar comprobaciones reproducibles de lock, lint, unitarias, manifiestos/plugins, contrato OpenAPI y configuración del despliegue soportado antes de poder integrarse.

#### Scenario: Cambio compatible
- **WHEN** un PR conserva todos los contratos rápidos
- **THEN** la lane rápida termina sin modificar archivos versionados ni emitir warnings de clientes de prueba obsoletos

#### Scenario: Snapshot o lock diverge
- **WHEN** OpenAPI no corresponde a la implementación o el lock no corresponde a `pyproject.toml`
- **THEN** CI falla indicando el artefacto que debe actualizarse

### Requirement: Integración con PostgreSQL real
CI MUST ejecutar los repositorios y servicios críticos contra PostgreSQL con pgvector real y un servicio de embeddings determinista, sin depender de servicios externos de producción.

#### Scenario: Aislamiento y revocación
- **WHEN** la suite crea usuarios, keys y memorias de propietarios distintos con el cache de identidad en cero
- **THEN** comprueba aislamiento en base de datos, revocación inmediata y ausencia de acceso cruzado

#### Scenario: Presupuesto de consultas
- **WHEN** la suite aumenta la cardinalidad de usuarios y memorias
- **THEN** comprueba los presupuestos constantes administrativos con conteo de consultas

### Requirement: Recorrido vertical de proceso real
CI MUST arrancar Granian con la aplicación FastAPI, FastMCP y PostgreSQL reales y MUST ejercer el transporte Streamable HTTP desde un cliente externo al proceso.

#### Scenario: Frontera MCP completa
- **WHEN** el recorrido intenta initialize y list sin token, luego usa una key válida con cache cero y finalmente la revoca
- **THEN** observa rechazo antes de sesión, operación válida con aislamiento y rechazo de la siguiente petición revocada

#### Scenario: Cache de identidad opt-in
- **WHEN** el recorrido habilita un TTL de identidad, cachea una key y la revoca
- **THEN** comprueba que la aceptación no supera la ventana configurada y que la primera petición posterior falla

#### Scenario: Error interno en proceso real
- **WHEN** una dependencia del recorrido lanza un sentinel interno
- **THEN** el sentinel queda ausente de la respuesta MCP y presente sólo en diagnóstico servidor sanitizado

#### Scenario: Shutdown del proceso
- **WHEN** CI termina el proceso Granian después de actividad MCP
- **THEN** el proceso finaliza dentro del timeout y los recursos se cierran sin errores de lifespan

### Requirement: Contrato de reverse proxy real
CI MUST verificar el endpoint MCP a través de una versión fijada de Traefik usando los mismos contratos de host, origen y proxy headers que producción.

#### Scenario: URL canónica detrás de Traefik
- **WHEN** el cliente usa el host permitido y `/mcp/`
- **THEN** initialize llega sin redirect y conserva `Authorization`

#### Scenario: Slash ausente o forwarding falsificado
- **WHEN** el cliente usa `/mcp` o intenta falsificar headers desde un peer no confiable
- **THEN** sólo se emite la ubicación relativa permitida y la atribución del cliente no confía en el valor falsificado

### Requirement: Detección de desfase docs↔superficie MCP
El gate rápido de entrega MUST comprobar que la documentación pública que enumera herramientas MCP coincide con el conjunto publicado por el servidor (once herramientas con los nombres canónicos). Un desfase MUST fallar el gate indicando el artefacto documental a corregir.

#### Scenario: Docs alineadas
- **WHEN** el README (y guías de superficie incluidas en el check) listan exactamente las once herramientas canónicas
- **THEN** el gate rápido no falla por superficie MCP

#### Scenario: Docs desfasadas
- **WHEN** la documentación pública afirma un conteo distinto u omite una herramienta publicada
- **THEN** CI falla nombrando el documento y el desfase
