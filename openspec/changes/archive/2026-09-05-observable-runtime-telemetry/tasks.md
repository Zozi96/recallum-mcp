## 1. Snapshot de métricas

- [x] 1.1 Crear un snapshot de métricas (Pydantic) que lea los contadores ya existentes: `TelemetryBuffer.dropped_events`, contadores de fallo de flush, latencia por herramienta desde el middleware, y la proporción de degradadas. Sin nueva infraestructura: sólo lectura de contadores en memoria. Verificación: test unitario del snapshot con valores sembrados.
- [x] 1.2 Añadir el endpoint al router de salud en `recallum/app.py` con respuesta tipada y sin pasar por `BearerAuthMiddleware` de MCP. Verificación: `tests/unit/test_app.py` cubre el endpoint y sus códigos.

## 2. Contadores de flush y latencia

- [x] 2.1 Si el middleware no cuenta ya fallos de flush como métrica, añadirlo (increments at `buffer.py:91`/fallo de `flush`). Verificación: test unitario en `tests/unit/test_telemetry.py` para fallo de flush observable.
- [x] 2.2 Exponer la proporción de `degraded_textual` en recall y el marcador de embedding en escritura como contadores agregados. Verificación: test unitario cubre el ratio tras forzar modo degradado.

## 3. Protección y documentación de la superficie

- [x] 3.1 Documentar en `docs/operations.md` el binding interno y el control de acceso del endpoint; ajustar `deploy/docker-compose.yml` si hay que publicar puerto o restringirlo. Verificación: escenario `Superficie de métricas no pública` cubierto por test que prueba que un token de agente no autoriza el endpoint.
- [x] 3.2 Confirmar que ninguna etiqueta deriva de query, UUID, token ni contenido de memoria (auditoría contra `Observabilidad HTTP segura`). Verificación: revisión del snapshot y caso en tests.

## 4. Validación global

- [x] 4.1 Ejecutar `uv run pytest tests/unit -q` completo. Verificación: suite unitaria verde.
- [x] 4.2 Actualizar el README o guía de operación si el endpoint pasa a ser superficie documentada. Verificación: docs coherentes con el endpoint real.
