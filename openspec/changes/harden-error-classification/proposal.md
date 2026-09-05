## Why

Dos fragilidades concretas en la superficie de errores, ambas ya acotadas en el código:

1. La deduplicación por índice activo se detecta comparando el texto de la excepción: `_is_dedup_integrity_error` busca la subcadena `uq_memories_active_dedup` en `str(exc)` cuando `orig.constraint_name` no la contiene (`recallum/memory/service.py:275-282`). Un cambio de driver, de versión de PostgreSQL o de nombre de índice convierte una violación de dedup en un error no clasificado que se reintenta como si no lo fuera (o viceversa), y hoy no hay señal hasta que ocurre en producción.
2. El perfil materializado devuelve `ProfileBlock(available=False)` de forma indistinguible tanto cuando el usuario no tiene perfil (estado legítimo) como cuando la base de datos falla durante el intento de reconstrucción o lectura (`service.py:1189` y `service.py:1506` tragan el `except Exception`). Un operador o un agente cliente no puede distinguir "no hay perfil" de "la capa de datos está rota".

## What Changes

- La detección de la violación de dedup se clasifica por código estructurado de PostgreSQL (SQLSTATE `23505`, unique violation) y nombre de restricción cuando el driver lo expone, en lugar de comparar texto libre de error.
- `ProfileBlock(available=False)` deja de servirse como respuesta a un fallo de infraestructura: los fallos de base de datos durante la lectura/reconstrucción del perfil se registran y propagan de forma que la superficie MCP traduce el error a su forma segura, en lugar de enmascararlo como "sin perfil". El caso legítimo "usuario sin perfil" sigue devolviendo `available=False`.
- Sin cambios en herramientas MCP, firma de métodos ni esquemas de respuesta; sólo cambia qué se considera error y qué se considera vacío.

## Capabilities

### New Capabilities

(ninguna)

### Modified Capabilities

- `agent-memory-lifecycle`: la deduplicación concurrente se clasifica por código estructurado, no por texto.
- `memory-profile`: un fallo de base de datos durante la lectura del perfil ya no se enmascara como "sin perfil"; sólo la ausencia legítima devuelve `available=False`.

## Impact

- Código: `recallum/memory/service.py` (`_is_dedup_integrity_error`, llamadores de `get_profile`/`_rebuild_profiles_for_keys` que tragan excepciones).
- Tests: casos nuevos en `tests/unit/test_service.py` (clasificación SQLSTATE) y `tests/unit/test_memory_profile.py` (fallo de DB no devuelve `available=False`); integración de dedup concurrente en `tests/integration/test_db.py` si hay base.
- Compatibilidad: ninguna externa; es un endurecimiento interno.
- Sin migraciones.
