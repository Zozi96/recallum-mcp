## Context

Recallum parte de un repositorio Python mínimo y se desplegará en un VPS Ubuntu 24.04 con 6 vCPU, 11.7 GiB de RAM, Docker Swarm, Dokploy y Traefik. El host ya ejecuta servicios internos de PostgreSQL, Redis, NATS y Valkey, pero ninguno de los PostgreSQL disponibles incluye pgvector y el PostgreSQL de Dokploy pertenece a la plataforma.

Los consumidores serán Codex y Claude Code desde el propio VPS y desde máquinas remotas. Habrá pocos usuarios conocidos, pero sus memorias deben permanecer totalmente aisladas. El sistema no puede depender de APIs de IA pagadas ni conservar conversaciones completas.

## Goals / Non-Goals

**Goals:**

- Proporcionar memoria persistente mediante herramientas MCP autenticadas.
- Guardar memorias atómicas de tipo `preference`, `decision`, `constraint` o `fact`.
- Separar memorias globales y memorias asociadas a un proyecto.
- Aislar usuarios en la aplicación y en PostgreSQL.
- Recuperar información mediante búsqueda híbrida textual y vectorial.
- Generar embeddings localmente con recursos adecuados para el VPS.
- Compartir la misma lógica entre FastMCP y los endpoints operativos de FastAPI mediante Dependency Injector.

**Non-Goals:**

- Persistir conversaciones completas o capturarlas automáticamente.
- Compartir memorias entre usuarios.
- Ejecutar un modelo generativo durante el guardado normal.
- Proporcionar dashboard, OAuth, organizaciones, roles o invitaciones.
- Añadir Redis, NATS, workers, colas, grafo de conocimiento o reranking externo.
- Mantener compatibilidad binaria con las APIs de Mem0 o Supermemory.

## Decisions

### FastAPI alojará FastMCP

La aplicación se construirá como una factory de FastAPI. Un servidor FastMCP 3.x expondrá su aplicación HTTP con `http_app(path="/")` y se montará en `/mcp`. El lifespan de FastMCP se compondrá con la inicialización y cierre de los recursos de Dependency Injector.

FastAPI expondrá únicamente endpoints operativos como liveness y readiness; el ciclo de vida de las memorias se realizará por MCP para evitar duplicar una API CRUD que el MVP no necesita.

### SQLAlchemy administrará el acceso y Alembic las migraciones

El acceso a PostgreSQL usará SQLAlchemy 2.x con `create_async_engine`, el dialecto `postgresql+asyncpg` y un `async_sessionmaker`. Cada llamada MCP obtendrá su propio `AsyncSession` y su propia transacción; ninguna sesión se compartirá entre tareas concurrentes.

Los modelos declarativos representarán `users`, `api_keys` y `memories`. El tipo `Vector(768)` integrará pgvector con SQLAlchemy, mientras que las consultas híbridas podrán usar SQLAlchemy Core cuando expresen mejor las funciones específicas de PostgreSQL.

Alembic será la única vía para cambiar el esquema. Las tablas y constraints convencionales podrán generarse desde metadata, pero las migraciones escribirán DDL explícito para `CREATE EXTENSION vector`, columnas `tsvector` generadas, índices HNSW, índices parciales y políticas RLS. La aplicación no ejecutará `create_all()` en startup.

### Dependency Injector administrará dependencias concretas

Un `DeclarativeContainer` contendrá configuración, `AsyncEngine`, `async_sessionmaker`, cliente HTTP de Ollama, autenticación, repositorio y servicio de memorias. El engine será un recurso de aplicación y el sessionmaker una factory reutilizable que producirá una sesión nueva por operación. Se usarán providers concretos, sin interfaces con una única implementación. Los overrides de providers aislarán PostgreSQL y Ollama en pruebas.

### Las herramientas MCP serán la interfaz del producto

FastMCP expondrá cinco herramientas:

- `remember`: guarda una memoria atómica validada.
- `recall`: busca memorias relevantes para una consulta.
- `context`: obtiene contexto global y de proyecto para iniciar o continuar una sesión.
- `list_memories`: enumera memorias con filtros y paginación limitada.
- `forget`: realiza borrado lógico de una memoria concreta.

Ninguna herramienta aceptará `user_id`. La identidad se derivará del token autenticado.

### La autenticación usará API keys aleatorias

Cada usuario tendrá una o más API keys generadas con entropía criptográfica. El servidor mostrará el secreto una sola vez y almacenará únicamente su hash SHA-256. Un middleware de FastMCP validará el header `Authorization: Bearer` antes de ejecutar cualquier herramienta y colocará la identidad en un `ContextVar` limitado a la petición.

No se añadirá OAuth porque los usuarios son pocos y conocidos. Las keys podrán revocarse individualmente.

### PostgreSQL aplicará aislamiento defensivo

Se desplegará una instancia PostgreSQL dedicada con pgvector; no se reutilizará el PostgreSQL interno de Dokploy ni el contenedor de desarrollo existente.

El esquema mínimo contendrá `users`, `api_keys` y `memories`. La tabla `memories` incluirá `user_id`, ámbito, proyecto opcional, categoría, contenido, hash normalizado, vector de 768 dimensiones, importancia, cliente de origen, metadata limitada y timestamps.

Todas las operaciones del repositorio se ejecutarán dentro de una transacción de `AsyncSession` que configure el usuario actual mediante `SET LOCAL`. Row-Level Security restringirá `memories` y `api_keys` a ese usuario. La aplicación también incluirá filtros explícitos por usuario; RLS actuará como segunda barrera.

El contenido será inmutable. `forget` establecerá `deleted_at`, y las búsquedas excluirán filas eliminadas. Un índice único parcial sobre usuario, ámbito y hash evitará duplicados exactos activos.

### Ollama generará embeddings locales

Ollama se ejecutará en CPU dentro de la red privada de Docker con `embeddinggemma:300m-qat-q4_0`. El modelo produce vectores de 768 dimensiones y cabe con margen en el VPS. Recallum llamará a la API de embeddings de Ollama de forma síncrona porque cada memoria es corta y el volumen inicial es bajo.

El agente consumidor entregará texto atómico; Recallum no ejecutará una segunda extracción generativa. Si en el futuro se añade captura automática, será un cambio separado y podrá usar un modelo local con salida estructurada.

### La búsqueda será híbrida y determinista

Cada memoria tendrá un `tsvector` generado con la configuración `simple` para tolerar contenido mixto en español, inglés y código. `recall` calculará candidatos por similitud coseno de pgvector y por ranking textual de PostgreSQL, fusionará ambos rankings con Reciprocal Rank Fusion y aplicará filtros de usuario, ámbito, proyecto y categoría.

No habrá reranker. `context` combinará memorias globales importantes con memorias relevantes del proyecto y aplicará límites de cantidad y caracteres para producir una respuesta compacta.

### El despliegue reutilizará la infraestructura existente

Dokploy ejecutará tres servicios: Recallum, PostgreSQL con pgvector y Ollama. Traefik publicará únicamente Recallum mediante HTTPS. PostgreSQL y Ollama permanecerán en una red privada y usarán volúmenes persistentes.

Los límites iniciales serán aproximadamente 512 MiB para Recallum, 2 GiB para PostgreSQL y 1.5 GiB para Ollama. La imagen de Recallum usará Python 3.13 para evitar depender del Python 3.14 instalado en el host y mantener compatibilidad amplia con FastMCP y sus dependencias.

## Risks / Trade-offs

- [Los agentes pueden olvidar llamar a `remember`] → Incluir instrucciones de integración claras; evaluar un hook de fin de sesión sólo con evidencia de pérdidas frecuentes.
- [Una memoria mal redactada produce recuperación deficiente] → Validar longitud, categoría y ámbito; devolver contenido y metadata para que el agente pueda corregir mediante `forget` y un nuevo `remember`.
- [Ollama no está disponible] → Readiness fallará; `remember` no persistirá una fila sin embedding y `recall` podrá degradarse a búsqueda textual mientras PostgreSQL siga disponible.
- [La búsqueda híbrida añade dos consultas] → Limitar candidatos y medir antes de introducir caché o reranking.
- [Una API key filtrada permite acceder a memorias privadas] → Mostrarla una sola vez, almacenar sólo hash, permitir revocación y mantener aislamiento RLS.
- [El borrado lógico conserva datos en disco] → Excluir inmediatamente la fila de todas las consultas y ejecutar purga física periódica durante mantenimiento y antes de restauraciones compartidas.

## Migration Plan

1. Desplegar PostgreSQL dedicado con los paquetes necesarios para pgvector.
2. Ejecutar `alembic upgrade head` para habilitar pgvector y crear usuarios, API keys, memorias, índices y políticas RLS.
3. Desplegar Ollama, descargar el modelo de embeddings y verificar readiness desde la red privada.
4. Desplegar Recallum sin exposición pública y ejecutar pruebas de integración internas.
5. Crear las API keys iniciales y probar aislamiento entre dos usuarios.
6. Publicar `/mcp` mediante Traefik y configurar Codex y Claude Code.
7. Activar backups diarios del volumen PostgreSQL y verificar una restauración.

El rollback consiste en retirar la ruta de Traefik y volver a la imagen anterior de Recallum. Las migraciones iniciales son aditivas y los volúmenes se conservarán; no se eliminarán datos automáticamente durante rollback.

## Open Questions

Ninguna para el MVP. La captura automática y el uso de un modelo generativo local quedan explícitamente diferidos.
