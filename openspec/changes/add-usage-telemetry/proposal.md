## Why

Recallum no registra actividad. Lo único que se aproxima es `last_used_at` de cada API key, y responde a "¿esta credencial sigue en uso?", no a "¿cómo se está usando la memoria?". No hay forma de saber cuántas veces se recupera, si la recuperación devuelve algo útil, con qué frecuencia el servicio de embeddings falla y obliga a degradar la búsqueda, ni si un proyecto concreto usa su memoria o la tiene abandonada.

Sin ese dato, las estadísticas del sitio de administración sólo pueden describir el inventario: cuántas memorias hay y de qué tipo. Eso dice qué se ha guardado, pero no si sirve de algo. La pregunta que motiva un panel de uso es la segunda.

El obstáculo es de diseño, no de esfuerzo. El camino de llamada de herramientas está explícitamente optimizado para no serializarse: `LAST_USED_REFRESH_INTERVAL` sacrifica exactitud para no escribir en cada llamada. Añadir una escritura por llamada revertiría esa decisión sin discutirla.

## What Changes

- Registrar cada llamada a una herramienta MCP con su resultado y su duración, sin incorporar una escritura sincrónica al camino de llamada.
- Registrar únicamente metadatos de la operación; no persistir el texto de las consultas ni el contenido de las memorias.
- Registrar cuándo una recuperación se sirvió degradada por indisponibilidad del servicio de embeddings.
- Tratar la actividad registrada como dato operativo, distinto del contenido de las memorias, con su propia regla de acceso.
- Exponer al usuario la actividad de su propia memoria: volumen de operaciones en el tiempo, reparto por herramienta y por proyecto, y frecuencia de degradación.
- Descartar la actividad antigua transcurrido un plazo de retención, para que el registro no crezca sin límite.
- Aceptar de forma explícita que un corte inesperado del proceso pierda la actividad todavía no volcada.

## Capabilities

### New Capabilities

- `agent-usage-telemetry`: Registro diferido de la actividad de herramientas MCP y su consulta agregada, sin contenido de usuario y sin penalizar el camino de llamada.

### Modified Capabilities

Ninguna. Las herramientas MCP conservan su comportamiento, sus argumentos y sus respuestas.

## Impact

- Añade una migración con el almacenamiento de actividad.
- Añade una etapa al encadenado de middleware de FastMCP, posterior a la autenticación, de modo que la actividad quede siempre atribuida a una identidad ya verificada.
- Introduce trabajo periódico en segundo plano para volcar y purgar, ligado al ciclo de vida de la aplicación.
- Introduce el primer dato del sistema que no está protegido por Row-Level Security, lo que obliga a fijar como norma qué puede contener.
- Alimenta las estadísticas de actividad del sitio de administración, tanto propias como agregadas.
