## Why

Codex y Claude Code necesitan una memoria persistente, privada y reutilizable entre sesiones sin depender de servicios de pago como Mem0 o Supermemory. El VPS actual tiene capacidad suficiente para alojar una solución propia basada en PostgreSQL, pgvector y embeddings locales.

## What Changes

- Añadir un servicio MCP remoto y local para que agentes autorizados guarden, consulten, enumeren y eliminen memorias.
- Guardar únicamente preferencias, decisiones, restricciones y hechos importantes; no persistir conversaciones completas.
- Aislar estrictamente las memorias por usuario mediante API keys individuales y controles en la base de datos.
- Organizar las memorias de cada usuario en ámbitos globales y por proyecto.
- Recuperar memorias mediante búsqueda híbrida semántica y textual, con resultados limitados y ordenados por relevancia.
- Generar embeddings localmente con Ollama para evitar APIs pagadas.
- Ejecutar el servicio con FastAPI, FastMCP y Dependency Injector sobre la infraestructura Docker, Dokploy y Traefik existente.

## Capabilities

### New Capabilities

- `agent-memory-lifecycle`: Creación, clasificación, enumeración y borrado explícito de memorias atómicas, privadas y aisladas por usuario.
- `agent-memory-retrieval`: Recuperación híbrida de memorias relevantes y generación de contexto compacto por usuario y proyecto.
- `mcp-agent-integration`: Acceso autenticado mediante herramientas FastMCP desde Codex y Claude Code, tanto local como remotamente.

### Modified Capabilities

Ninguna.

## Impact

- Sustituye el programa Python de ejemplo por un servicio web desplegable.
- Añade FastAPI, FastMCP, Dependency Injector, acceso asíncrono a PostgreSQL y migraciones de base de datos.
- Añade una instancia PostgreSQL dedicada con pgvector y un servicio Ollama privado con un modelo local de embeddings.
- Añade configuración de despliegue para Dokploy/Traefik, secretos de API keys, persistencia y backups.
- Expone únicamente HTTPS para Recallum; PostgreSQL y Ollama permanecen en la red privada de Docker.
