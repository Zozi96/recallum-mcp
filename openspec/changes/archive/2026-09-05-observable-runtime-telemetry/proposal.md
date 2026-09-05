## Why

La degradación del servicio es hoy invisible para el operador: el buffer de telemetría descarta eventos por desbordamiento con un contador `dropped_events` que no se expone en ninguna superficie (`recallum/telemetry/buffer.py:44,55`), los fallos de flush reencolan en silencio, y no hay endpoint de métricas ni exportación Prometheus. La única señal de latencia de herramientas son filas de base de datos; la caída de Ollama o de PostgreSQL durante la operación sólo se manifiesta como cambio de comportamiento del cliente, sin registro operativo. Sin esta superficie, las áreas 1 (degradación de embeddings) y 2 (rebuild asíncrono) del plan no se podrán observar cuando lleguen a producción.

## What Changes

- Nuevo endpoint de métricas operativas de solo operador (p.ej. `GET /metrics` en formato Prometheus, o JSON mínimo si se rechaza Prometheus; decisión en design) que expone: contador de eventos de telemetría descartados por desbordamiento, fallos de flush, latencia por herramienta MCP, proporción de respuestas `degraded_textual` en recall, proporción de escrituras con marcador de embedding no disponible, y estado de sondas de readiness.
- El endpoint NO reemplaza la persistencia de telemetría en base de datos (la consulta por usuario sigue en `agent-usage-telemetry`); agrega una vista operativa agregada y anónima.
- Acceso restringido: no es un endpoint MCP de agente; se protege con el mismo mecanismo de autenticación del operador o por binding a loopback/rol interno, y nunca expone contenido de memoria ni datos de usuario.

## Capabilities

### New Capabilities

(ninguna)

### Modified Capabilities

- `agent-usage-telemetry`: se añade la exposición operativa de métricas y el contador de drops pasa a ser observable.
- `service-runtime-resilience`: se registra la existencia del endpoint de métricas y su protección frente a exposición pública accidental.

## Impact

- Código: `recallum/telemetry/buffer.py` (exponer contadores ya existentes), `recallum/telemetry/middleware.py` (latencia por herramienta), `recallum/app.py` (router de métricas junto a `/healthz` y `/readyz`), nueva lectura de contadores en `recallum/container.py`.
- Tests: `tests/unit/test_telemetry.py`, `tests/unit/test_app.py`.
- Despliegue: posible exposición del puerto/ruta en `deploy/docker-compose.yml` y nota en `docs/operations.md`.
- Sin migraciones; los datos de métricas son en memoria, derivados de contadores existentes.
