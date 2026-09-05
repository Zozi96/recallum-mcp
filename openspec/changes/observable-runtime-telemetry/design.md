## Context

Estado actual (verificado):

- `TelemetryBuffer` (`recallum/telemetry/buffer.py:18-44`) ya mantiene `dropped_events` (contador en memoria) y registra fallos de flush con `logger.warning("tool activity batch flush failed", exc_info=True)` sin superficie consultable. El límite de cola y el `popleft` del desbordamiento están en los mismos puntos.
- `recallum/telemetry/middleware.py` registra la actividad por herramienta como eventos; `_result_metrics` (`middleware.py:22`) existe pero sólo alimenta la persistencia en base, no una vista en tiempo real.
- La app ya sirve `/healthz` (liveness sin dependencias) y `/readyz` (readiness con sondas a PostgreSQL y Ollama) desde `create_health_router` en `recallum/app.py:136-204`, con el patrón de router FastAPI y respuestas tipadas Pydantic.
- El despliegue en `deploy/entrypoint.sh` corre `workers=1`, así que los contadores en memoria son coherentes (no hay agregación multi-proceso que resolver).

## Goals / Non-Goals

**Goals:**

- Hacer visible la pérdida de telemetría (drops por desbordamiento, fallos de flush) sin rebuscar logs.
- Hacer visible el modo degradado (embeddings) y la latencia por herramienta en tiempo real.
- Mantener la superficie libre de datos sensibles y de cardinalidad controlada.

**Non-Goals:**

- No se introduce un sistema de métricas de terceros (Prometheus/OpenTelemetry) como dependencia obligatoria; el formato se decide en diseño y si no encaja en el stack actual, se expone JSON mínimo.
- No se añaden dashboards ni alertas; eso queda en el operador.
- No se cambia la persistencia de telemetría por usuario: la consulta histórica sigue en base.

## Decisions

1. **Endpoint propio junto al health router.** Se añade un `GET /metrics` (o `GET /operational-metrics` si el nombre colisiona con convenciones futuras) al router de salud, no a la superficie MCP de agente. Razón: el health router ya tiene el patrón de respuesta operativa, no pasa por `BearerAuthMiddleware` de MCP ni por el traductor de errores de herramientas, y su acceso se controla en el boundary de despliegue. Alternativa considerada: exponer métricas como herramienta MCP — rechazada, mezclaría operador y agente en la misma superficie y exigiría pasar contenido operativo por el contrato de errores MCP.

2. **Contadores en memoria, derivados de los existentes.** Los contadores ya viven en `TelemetryBuffer` y en el middleware; la superficie sólo los lee. No se introduce `prometheus_client` ni un registro global: se compone un snapshot Pydantic desde `container` en el handler. Alternativa considerada: adoptar `prometheus_client` y su formato de exposición — rechazada como dependencia nueva si no está ya en `pyproject.toml` (no lo está); si en una revisión posterior se quiere scrape nativo, la misma superficie puede cambiar de formato sin cambiar los contadores subyacentes.

3. **Acceso por binding + token de operador, no por rol de usuario.** Se protege como un endpoint de operación: binding a la interfaz interna en despliegue (loopback o red privada en `docker-compose.yml`) y/o token de operador, documentado en `docs/operations.md`. No se apoya en la autenticación de usuario/agente porque las métricas son del proceso, no de un usuario.

4. **Sin datos de usuario.** Cada métrica se audita contra el requisito `Observabilidad HTTP segura`: contadores de drops/fallos son números; latencias por herramienta usan la plantilla de herramienta (cardinalidad fija y conocida); proporción degradada es un ratio. Ninguna etiqueta deriva de query, UUID, token ni contenido de memoria.

## Risks / Trade-offs

- **Exposición accidental del endpoint**: riesgo principal. Mitigación: binding interno por defecto en los compose, y prueba de que un token de agente no lo autoriza (escenario `Superficie de métricas no pública`).
- **Métricas de un solo proceso**: con `workers=1` no hay problema, pero si algún día se escala a múltiples workers la superficie por proceso deja de ser la vista agregada. Queda fuera de alcance y se anota en `docs/operations.md`.
- **Decisión abierta (Prometheus vs JSON mínimo)**: se documenta en este design como decisión 2 con el criterio de no añadir dependencias; si el equipo prefiere el formato Prometheus, se cambia en una iteración posterior sin tocar los contadores.
