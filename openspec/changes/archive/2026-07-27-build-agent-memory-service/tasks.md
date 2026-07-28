## 1. Base de aplicación

- [x] 1.1 Sustituir el programa de ejemplo por una estructura mínima de aplicación FastAPI con Python 3.14.
- [x] 1.2 Añadir y bloquear dependencias para FastAPI, FastMCP 3.x, Dependency Injector, SQLAlchemy 2.x, asyncpg, pgvector, Alembic y cliente HTTP.
- [x] 1.3 Crear configuración validada desde variables de entorno para base de datos, Ollama, autenticación y límites de memoria.
- [x] 1.4 Crear el `DeclarativeContainer` con `AsyncEngine`, `async_sessionmaker`, configuración y providers concretos, incluyendo overrides utilizables en pruebas.

## 2. Persistencia y aislamiento

- [x] 2.1 Configurar Alembic con su template async y metadata declarativa de SQLAlchemy sin ejecutar `create_all()` en la aplicación.
- [x] 2.2 Añadir una migración Alembic para habilitar pgvector y crear `users`, `api_keys` y `memories` con vector de 768 dimensiones.
- [x] 2.3 Añadir DDL explícito en Alembic para `tsvector`, índices HNSW, deduplicación parcial y políticas Row-Level Security.
- [x] 2.4 Implementar el mecanismo de `AsyncSession` por operación que ejecuta `SET LOCAL` dentro de cada transacción autenticada.
- [x] 2.5 Implementar el repositorio asíncrono con SQLAlchemy para crear, obtener, enumerar, buscar y borrar lógicamente memorias.
- [x] 2.6 Añadir pruebas de integración que ejecuten las migraciones y demuestren deduplicación y aislamiento entre dos usuarios reales de PostgreSQL.

## 3. Embeddings y lógica de memoria

- [x] 3.1 Implementar el cliente de Ollama para embeddings con timeouts y errores acotados.
- [x] 3.2 Implementar validación y normalización de contenido, categoría, ámbito, proyecto, importancia y metadata.
- [x] 3.3 Implementar `remember`, generando el embedding antes de persistir y devolviendo la memoria existente ante duplicados exactos.
- [x] 3.4 Implementar `recall` con candidatos vectoriales y textuales fusionados mediante Reciprocal Rank Fusion.
- [x] 3.5 Implementar fallback textual marcado como degradado cuando Ollama no pueda generar el embedding de una consulta.
- [x] 3.6 Implementar `context`, `list_memories` y `forget` respetando filtros, límites y borrado lógico.
- [x] 3.7 Añadir pruebas unitarias del servicio usando overrides del repositorio y cliente de embeddings.

## 4. Autenticación y FastMCP

- [x] 4.1 Implementar generación, hashing, consulta y revocación de API keys sin persistir el secreto original.
- [x] 4.2 Añadir un CLI administrativo mínimo con stdlib para crear usuarios, emitir keys y revocarlas.
- [x] 4.3 Implementar middleware FastMCP que valide `Authorization: Bearer` y establezca la identidad de la petición.
- [x] 4.4 Exponer `remember`, `recall`, `context`, `list_memories` y `forget` con esquemas validados que no acepten `user_id`.
- [x] 4.5 Añadir pruebas MCP para descubrimiento, token válido, token inválido, token revocado y ausencia de acceso cruzado.

## 5. Servidor y operación

- [x] 5.1 Montar la aplicación HTTP de FastMCP en `/mcp` dentro de la factory FastAPI y componer correctamente los lifespans.
- [x] 5.2 Añadir endpoints de liveness y readiness sin datos sensibles, comprobando PostgreSQL y Ollama sólo en readiness.
- [x] 5.3 Añadir logging estructurado que excluya API keys, contenido de memorias y headers de autorización.
- [x] 5.4 Añadir una prueba de aplicación ASGI que valide startup, health checks y cierre limpio de recursos.

## 6. Despliegue y documentación

- [x] 6.1 Crear imágenes y configuración Docker para Recallum, PostgreSQL con pgvector y Ollama en una red privada.
- [x] 6.2 Añadir configuración de Dokploy/Traefik y límites de recursos sin publicar PostgreSQL ni Ollama.
- [x] 6.3 Documentar descarga persistente de `embeddinggemma:300m-qat-q4_0`, variables de entorno y migraciones.
- [x] 6.4 Documentar configuración MCP para Codex y Claude Code con el endpoint HTTPS y API key.
- [x] 6.5 Configurar backups diarios de PostgreSQL y documentar una restauración verificada. *(Cerrada sin ejecución de infraestructura por decisión explícita del propietario el 2026-07-27. El procedimiento permanece documentado en `docs/operations.md`.)*
- [x] 6.6 Ejecutar migraciones y smoke tests en el VPS, incluyendo acceso local, acceso remoto y aislamiento entre dos usuarios. *(Cerrada sin ejecutar la validación remota de infraestructura por decisión explícita del propietario el 2026-07-27. El smoke test local previo y el runbook permanecen documentados en `docs/operations.md`.)*

## 7. Correcciones posteriores al review

- [x] 7.1 Asegurar que el rol propietario de tablas no sea superusuario ni tenga `BYPASSRLS`, manteniendo autenticación y `FORCE RLS` compatibles.
- [x] 7.2 Ejecutar Alembic como job previo al servicio y hacer que readiness valide esquema, ownership y seguridad del rol.
- [x] 7.3 Corregir la combinación de filtros `scope`/`project` y el presupuesto estricto de caracteres de `context`.
- [x] 7.4 Convertir los checks de autenticación del smoke test en aserciones efectivas.
- [x] 7.5 Restringir permisos de backups, hacer restores atómicos y añadir purga física explícita de soft-deletes.
