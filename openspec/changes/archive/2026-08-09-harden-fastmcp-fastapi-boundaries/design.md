## Context

Recallum sirve una aplicación FastAPI raíz con Granian, monta la API web en `/api/v1` y la aplicación Streamable HTTP de FastMCP en `/mcp`. La identidad MCP se resuelve actualmente dentro de middleware de operaciones: protege llamadas de herramientas y recursos, pero ocurre después de que el transporte acepte `initialize` y permite descubrir herramientas sin token. FastMCP 3.4.4 también deja `mask_error_details` desactivado por defecto, por lo que una excepción no controlada o un `ToolError` construido con el texto de `EmbeddingError` puede revelar detalles internos.

La aplicación ya conserva aislamiento por usuario, revocación inmediata por defecto, cookies web confinadas, CORS exacto, lifespans compuestos y una base extensa de pruebas unitarias. El diseño preserva esas propiedades. No requiere migración de datos y evita introducir infraestructura distribuida mientras el runtime MCP mantenga sesiones en memoria.

El camino soportado es la imagen que ejecuta Granian mediante `deploy/entrypoint.sh`. `deploy/dokploy-compose.yml` es una alternativa no utilizada: no se reparará ni se usará como criterio de release en este cambio.

## Goals / Non-Goals

**Goals:**

- Cerrar autenticación y confidencialidad de errores en la frontera HTTP/MCP, antes de asignar estado de sesión o ejecutar lógica de negocio.
- Hacer deterministas y comprobables los contratos de proxy, límites, validación, startup, readiness, observabilidad y escalado.
- Mantener alineados los esquemas FastAPI, FastMCP y de dominio en los campos donde una coerción cambia el significado.
- Convertir los hallazgos en gates de CI reproducibles y en tareas que puedan asignarse por workstream.
- Eliminar N+1 y respuestas administrativas sin cota sin ampliar el acceso de administradores a contenido de memorias.

**Non-Goals:**

- Reparar, promover o validar `deploy/dokploy-compose.yml`.
- Cambiar autorización, aislamiento por propietario o semántica del dominio de memorias.
- Incorporar Redis, sesiones MCP compartidas o rate limiting distribuido.
- Habilitar múltiples workers o réplicas antes de validar un transporte stateless o una estrategia de afinidad/estado compartido.
- Eliminar inmediatamente el endpoint GET de búsqueda; se conservará durante una ventana de deprecación.
- Añadir contenido, query strings, cookies, tokens, correos o identificadores de usuario a logs o métricas HTTP.

## Decisions

### 1. La autenticación MCP se moverá al transporte y la identidad se enlazará sin una segunda consulta

Se añadirá un `TokenVerifier` de FastMCP respaldado por el `TokenAuthenticator` existente y se pasará como `auth` al construir `FastMCP`. Por cada petición HTTP, el verificador resolverá la API key y devolverá un `AccessToken` con `subject=user_id`, `client_id=api_key_id` y claims mínimos para reconstruir `Identity`. No se incluirán secretos adicionales en claims ni se registrará el objeto `AccessToken`.

El middleware de operaciones dejará de releer `Authorization` y de autenticar contra PostgreSQL. Obtendrá el token ya verificado mediante la API pública de dependencias de FastMCP, validará los claims y abrirá `identity_scope` alrededor de herramientas, recursos y listados. Así se conservan `require_identity()` y la telemetría existentes sin pagar dos consultas. Una ausencia o claim malformado fallará cerrado.

La autenticación de transporte cubrirá `initialize`, `ping`, listados, lecturas y llamadas antes de crear una sesión. El verifier se invocará en cada petición HTTP y no añadirá un cache propio. Con `identity_cache_seconds=0`, `TokenAuthenticator` consultará el estado activo y una key revocada fallará en la siguiente petición incluso dentro de una sesión ya iniciada. Si un operador habilita explícitamente el cache existente, el servicio conservará su contrato actual: la key puede vivir como máximo hasta ese TTL, nunca se extiende al reutilizarla, se emite una advertencia operativa y la ventana se prueba con reloj determinista. El perfil de producción recomendado y usado por los tests verticales mantendrá el valor en cero.

Alternativas consideradas:

- Extender sólo `BearerAuthMiddleware` con más hooks: no protege negociación HTTP ni asignación de sesión.
- Autenticar en transporte y volver a consultar en cada herramienta: es seguro pero duplica presión sobre el pool y crea dos fuentes de identidad.
- Usar un verifier de desarrollo o tokens autocontenidos: no preserva la revocación inmediata respaldada por PostgreSQL.

### 2. Los errores cliente serán una lista permitida; todo lo demás se enmascara y se registra

`FastMCP` se construirá con `mask_error_details=True`. Los errores de validación de dominio que ya son seguros conservarán mensajes accionables. Los fallos de embeddings producirán exactamente el mensaje público `embedding service unavailable`, y el detalle original se registrará con stack y request ID sólo en servidor. Ningún `ToolError` explícito interpolará excepciones de infraestructura, URLs o cadenas de conexión.

Las pruebas inyectarán sentinelas únicos en excepciones inesperadas y de embeddings y comprobarán que no aparecen en respuesta, logs cliente ni contenido MCP. También comprobarán que el log servidor sí conserva evidencia diagnóstica sin `Authorization`, API keys ni cuerpos.

Alternativa considerada: confiar sólo en `mask_error_details`. FastMCP no enmascara un `ToolError` deliberado, por lo que no resuelve la interpolación actual de `EmbeddingError`.

### 3. Habrá una frontera ASGI común para proxy confiable, tamaño, rate limit, request ID y cache

La aplicación raíz incorporará middleware ASGI pequeño, inyectable y probado con reloj determinista. Resolverá la IP cliente desde el peer inmediato y usará únicamente `X-Forwarded-For` para atribución. Si el peer pertenece a los CIDR confiables configurados, recorrerá la cadena de IPs de derecha a izquierda: descartará cada salto que también sea confiable y se detendrá en la primera IP no confiable, que será el cliente atribuido. Valores malformados, una cadena sin cliente o cualquier header enviado por un peer no confiable se ignorarán y se atribuirán al peer inmediato. Así un atacante no puede controlar la IP elegida anteponiendo valores.

La misma frontera aplicará límites antes de parsear Pydantic o crear sesiones:

- cuerpo general web/MCP: 1 MiB;
- cuerpo de login: 16 KiB;
- contraseña en login y confirmaciones: máximo 256 caracteres;
- login fallido: bucket por IP y por combinación IP + hash del correo normalizado, con defaults de 30 intentos/5 min por IP y 5 intentos/5 min por combinación;
- autenticación MCP inválida: 60 intentos/min por IP;
- máximo 10 000 buckets con expiración y eviction determinista.

El contador verificará bytes recibidos para que `Transfer-Encoding: chunked` no evada `Content-Length`. Un exceso de cuerpo devolverá `413`; un bucket agotado devolverá `429` con `Retry-After`. Los valores serán configuración tipada y los defaults podrán ajustarse con telemetría. Mientras se mantenga el contrato de un solo worker, el limiter en memoria ofrece una política consistente; habilitar réplicas exigirá reemplazarlo o mover la política al edge.

Todas las respuestas bajo `/api/v1`, incluidas login y logout, llevarán `Cache-Control: no-store`; las compatibles llevarán también `Pragma: no-cache`. El middleware generará o validará un request ID acotado y lo devolverá en `X-Request-ID`.

Alternativas consideradas:

- Depender sólo de Traefik: su configuración no vive en este repositorio y no puede probarse junto al contrato de aplicación.
- Añadir un servicio distribuido de rate limit: contradice el alcance y no aporta valor mientras el runtime soportado sea una sola instancia.

### 4. `/mcp/` será canónico y la protección Host/Origin será explícita

FastMCP se montará con protección de host/origen habilitada y allowlists derivadas de configuración tipada. Producción no aceptará wildcard; desarrollo podrá declarar localhost explícitamente. La ruta exacta `/mcp/` atenderá sin redirect. `/mcp` tendrá una respuesta explícita `308` con `Location: /mcp/` relativa, nunca una URL absoluta derivada de headers no confiables. Los instaladores y documentación seguirán normalizando la URL exacta con slash y podrán continuar rechazando redirects.

La configuración de producción deberá declarar hostname público, orígenes permitidos y CIDR de Traefik. Un valor inválido o wildcard inseguro fallará en startup.

Alternativas consideradas:

- Confiar en el redirect automático de Starlette: puede construir `Location` con esquema/host incorrectos detrás del proxy.
- Aceptar cualquier host porque Traefik ya enruta: amplía exposición ante Host-header/DNS rebinding y dificulta pruebas locales equivalentes.

### 5. La validación estricta se aplicará a tipos con ambigüedad semántica, no globalmente

Se crearán aliases Pydantic compartidos para enteros y strings críticos (`importance`, límites, offsets, tamaños y campos equivalentes). Los enteros usarán validación estricta y rangos de dominio, de modo que `true`, `false`, floats y strings numéricos no se conviertan silenciosamente. FastAPI y FastMCP reutilizarán esos aliases, y las pruebas atravesarán ambos transportes.

No se activará coerción cero de forma global sin una matriz de compatibilidad de clientes: algunos argumentos no críticos de agentes pueden depender de conversiones benignas. Cada endurecimiento adicional deberá quedar cubierto por contrato.

### 6. Startup usará cleanup transaccional y readiness tendrá un presupuesto total

El lifespan de aplicación usará `AsyncExitStack`. El cierre del contenedor se registrará antes de ejecutar validadores de exposición; el stop de telemetría se registrará inmediatamente después de un `start()` exitoso. El orden LIFO garantizará telemetría → clientes HTTP → engine y hará cleanup exactamente una vez en startup parcial, shutdown normal y cancelación.

`/readyz` ejecutará PostgreSQL y embeddings concurrentemente con timeout por dependencia de 2 s y presupuesto total de 3 s, configurables. Excepciones y timeouts se traducirán a un cuerpo `503` estable sin detalle interno. El engine tendrá límites explícitos de checkout/conexión/comando coherentes con ese presupuesto. `/healthz` seguirá siendo liveness puro y no dependerá de PostgreSQL u Ollama.

Alternativa considerada: probes secuenciales. Acumulan latencias y pueden dejar ocupada la petición indefinidamente si una dependencia ignora su timeout.

### 7. El runtime soportado seguirá stateful y de una sola instancia hasta demostrar lo contrario

El entrypoint declarará un worker Granian de forma explícita. La configuración fallará si solicita más de un worker mientras `stateless_http` no esté habilitado mediante una decisión y suite de compatibilidad posterior. La documentación operativa declarará una réplica; CI comprobará ese manifiesto soportado. No se afirmará soporte horizontal por el mero hecho de que FastAPI sea ASGI.

### 8. La observabilidad HTTP será de baja cardinalidad y privacy-safe

Un middleware compartido medirá método, plantilla de ruta, status, latencia y request ID. Para rutas montadas se registrará una plantilla normalizada, no el path con UUIDs. Nunca se registrarán query string, cuerpo, cookies, `Authorization`, email, token ni contenido de memoria. Los request IDs entrantes que no cumplan longitud/alfabeto se reemplazarán.

La búsqueda canónica pasará a `POST /me/memories/search` con `query` en JSON. El GET actual seguirá una versión como deprecated, devolverá headers de deprecación/sunset y no se incluirá su query en telemetría. Después de observar adopción podrá retirarse en un cambio separado.

### 9. OpenAPI modelará la cookie y los errores; administración usará consultas set-based y páginas

La dependencia web usará un esquema `APIKeyCookie`/`Security` para que OpenAPI marque todas las rutas protegidas y deje login como público. El snapshot incluirá `401`, `403`, `413`, `422`, `429` y `503` donde correspondan, junto con la deprecación de GET search.

`GET /admin/users` aceptará `limit` y `offset`, con default 100 y máximo 200, mantendrá la lista como cuerpo y publicará el total en `X-Total-Count`. Esto cambia el comportamiento de clientes que asumían una lista completa; la UI administrativa se actualizará en el mismo release. El volumen por usuario en agregados también será paginado o separado del resumen global para que ninguna respuesta crezca sin cota.

Repositorios nuevos harán conteos de keys y memorias mediante joins/subconsultas agrupadas y comprobarán mismatch de modelo con una consulta existencial global. Las pruebas de query budget exigirán un número constante de consultas al pasar de pocos a miles de usuarios. Los agregados seguirán siendo sólo recuentos y no abrirán acceso a contenido ajeno.

### 10. FastMCP tendrá un rango compatible y una única costura para APIs privadas

`pyproject.toml` acotará FastMCP a la línea compatible actual (`>=3.4,<4`) y `uv.lock` seguirá siendo la fuente reproducible de producción. Los usos necesarios de `_list_resources`, `_list_resource_templates` y `_list_prompts` se concentrarán en un módulo de compatibilidad con error de startup descriptivo. Ningún otro módulo llamará API privada.

CI probará primero el lock exacto. Una lane de candidato resolverá la última versión permitida: será informativa en PRs ordinarias y obligatoria para PRs que cambien FastMCP o el lock; también correrá de forma programada. Una incompatibilidad no actualizará producción silenciosamente.

Alternativas consideradas:

- Pin exacto sólo en `pyproject.toml`: reduce señal temprana y duplica el rol del lock.
- Mantener `>=3.0` sin límite: permite que una actualización del lock cruce una versión mayor incompatible.

### 11. CI separará gates rápidos, PostgreSQL real y recorrido vertical

La lane rápida ejecutará `uv lock --check`, Ruff, unitarias, pruebas de manifiestos/plugins, snapshot OpenAPI y validación de Compose soportado. La lane de integración levantará PostgreSQL con pgvector y un stub HTTP determinista de Ollama; cubrirá repositorios, aislamiento, revocación y query budgets.

La lane vertical arrancará un proceso Granian real sobre puertos efímeros y probará Streamable HTTP de extremo a extremo: rechazo de initialize/list sin token, uso válido, revocación en sesión existente, aislamiento, error sentinel, readiness y shutdown. Una prueba con Traefik fijado verificará host/origin, headers reenviados y `/mcp` frente a `/mcp/`. Los jobs archivarán diagnóstico sanitizado y nunca secretos.

## Risks / Trade-offs

- [Clientes MCP que no reenvían `Authorization` en cada petición dejan de funcionar] → probar Codex, Claude Code y Cursor contra el recorrido vertical antes de desplegar; mantener documentación de `/mcp/` y token actualizada.
- [Una allowlist o CIDR incorrectos bloquean tráfico legítimo] → validación de configuración, smoke test detrás de Traefik y rollback por imagen/configuración anterior.
- [El limiter en memoria se reinicia al desplegar y no escala entre réplicas] → aceptar esta propiedad bajo el contrato de una instancia; exigir diseño distribuido antes de escalar.
- [Límites por cuenta pueden usarse para lockout dirigido] → combinar bucket de IP y tupla, no bloquear una cuenta globalmente y no revelar qué bucket se agotó.
- [Validación estricta rechaza payloads antes aceptados por coerción] → limitarla a tipos ambiguos críticos, devolver errores de esquema accionables y probar clientes reales.
- [Paginación administrativa cambia expectativas de la UI] → desplegar servidor y UI juntos, usar parámetros opcionales y `X-Total-Count`, y documentar el máximo.
- [La lane de FastMCP candidato falla por un release upstream sin afectar el lock] → mantenerla informativa en PRs no relacionadas, pero bloquear upgrades hasta resolver el contrato.
- [Logs de diagnóstico de excepciones capturan accidentalmente datos] → no loguear argumentos/cuerpos, sanitizar campos estructurados y añadir pruebas de ausencia de sentinelas secretos.

## Migration Plan

1. Añadir gates CI y pruebas de regresión inicialmente rojas para auth de transporte y error masking; conservar fixtures para comparar el comportamiento actual.
2. Implementar `TokenVerifier`, binding de claims y `mask_error_details`; desplegar primero como P0 y verificar initialize/list/call, revocación inmediata con cache cero, ventana exacta con cache opt-in e aislamiento con los tres clientes soportados.
3. Añadir configuración de host/origin/proxy, ruta relativa, límites, request ID y no-cache. Cargar hostname/CIDR de Traefik y ejecutar smoke tests antes de promover.
4. Migrar startup/readiness, aliases estrictos, OpenAPI y POST search. Publicar deprecación de GET search durante al menos un release.
5. Introducir consultas set-based y paginación administrativa junto con la actualización de UI; validar query budget con cardinalidad alta.
6. Acotar FastMCP, encapsular APIs privadas y activar las lanes locked/candidate/vertical como gates según su política.
7. Mantener una sola réplica y un worker. Observar tasas de `401`, `413`, `429`, latencia y readiness sin registrar payloads.

Rollback: no hay migraciones de esquema. Cada fase puede volver a la imagen y configuración previas. Si la autenticación de transporte rompe un cliente soportado, se revierte la imagen completa; no se dejará un flag que reactive discovery anónimo. Los nuevos campos de configuración tendrán defaults locales seguros y producción validará los obligatorios.

## Open Questions

- Operaciones debe proporcionar los CIDR exactos de Traefik y el hostname/origen público por entorno antes del despliegue; no se inferirán de `X-Forwarded-*` ni se usará wildcard.
- Los defaults de rate limit y timeouts anteriores son el punto de partida. Se ajustarán sólo con telemetría agregada posterior, sin cambiar códigos ni headers del contrato.
