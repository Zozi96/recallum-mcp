## Why

Hoy toda la administración de Recallum vive en `recallum-admin`, un CLI que sólo puede ejecutarse dentro del contenedor. No existe forma de revisar, buscar ni curar las memorias propias sin pasar por un agente, y no existe ninguna credencial apta para un navegador: la API key es el secreto que usan Codex y Claude Code, y ponerla en el cliente web la expondría a XSS sin posibilidad de rotarla por sesión.

Se va a construir un sitio de administración (`recallum-ui`) servido en `memory.zozbit.com` contra la API en `recallum.zozbit.com`. Antes de cualquier endpoint de datos hace falta la pieza que hoy no existe: identidad de navegador, separada por completo de la identidad de agente.

Esta change revierte de forma deliberada parte de un Non-Goal de `build-agent-memory-service` ("proporcionar dashboard, OAuth, organizaciones, roles o invitaciones"). Se reabre únicamente lo mínimo: sesiones web y una distinción de administrador. Quedan fuera OAuth, organizaciones e invitaciones.

## What Changes

- Añadir credencial de acceso web a `users` mediante contraseña opcional, de modo que un usuario sin contraseña conserve acceso MCP y no tenga acceso web.
- Añadir la marca de administrador a `users`, sin la cual no existe hoy ninguna distinción de rol.
- Introducir sesiones de navegador en almacenamiento propio, independiente de las API keys, con caducidad por inactividad, tope absoluto y rotación del testigo.
- Detectar la reutilización de un testigo ya rotado como indicio de robo y revocar toda la cadena de sesión afectada.
- Exponer inicio de sesión, cierre de sesión y consulta de la identidad autenticada bajo `/api/v1`.
- Entregar la sesión en una cookie inaccesible a JavaScript, restringida al host de la API y a la ruta `/api/v1`, de forma que nunca acompañe a una llamada MCP.
- Permitir peticiones autenticadas desde el origen del sitio web sin ampliar el acceso al endpoint MCP.
- Añadir a `recallum-admin` la asignación de contraseña y la concesión de administrador, necesarias para habilitar al usuario ya existente en la base de datos.

## Capabilities

### New Capabilities

- `web-session-auth`: Identidad de navegador basada en contraseña y sesión renovable, aislada de la identidad de agente, con administración de credenciales web desde el CLI.

### Modified Capabilities

Ninguna. Las herramientas MCP y su autenticación por API key no cambian.

## Impact

- Añade una migración que amplía `users` y crea el almacenamiento de sesiones web.
- Añade una dependencia de derivación de claves para contraseñas; los hashes de API key siguen siendo SHA-256 sobre testigos aleatorios.
- Introduce el primer origen de navegador permitido; el endpoint MCP no queda alcanzable desde páginas web.
- Introduce la primera superficie HTTP autenticada fuera de `/mcp`, lo que obliga a que la validación de arranque siga garantizando que MCP no expone nada más que herramientas.
- Habilita las changes posteriores de API de autoservicio, telemetría de uso y consola de administración.
