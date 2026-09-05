## Why

Cada mutación de memoria (`remember`, `update`, `merge_memories`, `reconfirm`, `forget`) paga en la misma petición del cliente una reconstrucción completa del perfil: `_rebuild_profiles_for_memory` recorre las memorias activas del usuario y hace un upsert CAS por clave afectada tras el commit. El coste crece con el tamaño del corpus del usuario y se serializa dentro de la latencia de herramienta que el agente cliente espera; el sistema ya dispone de una vía de reconstrucción perezosa al leer (`Reconstrucción perezosa al leer`) y de una generación que marca las claves pendientes, así que el trabajo ansioso no compra corrección, sólo anticipación.

## What Changes

- La reconstrucción del perfil tras una mutación deja de ejecutarse en línea en la petición de escritura: la mutación incrementa la generación, marca las claves afectadas como pendientes y devuelve; la materialización la repone un trabajador en segundo plano o la próxima lectura (reconstrucción perezosa ya existente).
- Una mutación con la reconstrucción diferida MUST seguir garantizando que un `context`/`profile` posterior nunca sirve un perfil más viejo que la última mutación confirmada: la lectura compara la generación materializada con la del corpus y reconstruye el slice estático en el momento si difiere (mecanismo ya existente).
- **BREAKING** temporal/perceptual: el perfil materializado puede quedar desactualizado durante una ventana corta tras la escritura hasta que el trabajador o la lectura lo repone; el contrato de corrección se mantiene vía la reconstrucción perezosa, pero un lector que no pase por la vía perezosa (acceso directo a la fila) verá datos obsoletos.
- Comportamiento interno, no se añaden herramientas MCP ni se cambia la firma de ninguna.

## Capabilities

### New Capabilities

(ninguna)

### Modified Capabilities

- `memory-profile`: `Reconstrucción tras mutaciones` deja de ser síncrona en la petición; `Generation sólo por mutación de corpus` ya describe las claves "pendientes de reconstrucción" y se alinea con el diferido.
- `agent-memory-retrieval`: se añade un requisito que fija que `context` nunca sirve un perfil más viejo que la última mutación confirmada, reutilizando la lectura perezosa existente como red de seguridad (no cambia el comportamiento de `context` en sí).

## Impact

- Código: `recallum/memory/service.py` (`remember`, `_remember_in_session`, `update`, `merge_memories`, `reconfirm`, `forget`, `_rebuild_profiles_for_memory`, `_rebuild_profiles_for_keys`), ciclo de vida en `recallum/app.py` / `recallum/container.py` si se añade trabajador en segundo plano.
- Tests: `tests/unit/test_memory_profile.py`, `tests/unit/test_service.py`; posible escenario de integración para el trabajador.
- Operación: una tarea más en el ciclo de vida del proceso (con el patrón del `TelemetryBuffer`); sin migraciones de base de datos.
- Rendimiento esperado: la latencia de escritura deja de escalar con el tamaño del corpus.
