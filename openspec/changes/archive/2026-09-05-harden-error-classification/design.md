## Context

Estado actual (verificado sobre el código):

- `_is_dedup_integrity_error` (`recallum/memory/service.py:275-282`) primero inspecciona `exc.orig.constraint_name`, y si no lo encuentra, cae a `"uq_memories_active_dedup" in str(exc)`. El fallback de texto es el punto frágil: un mensaje de driver reformateado o un índice renombrado lo rompen silenciosamente. El patrón asyncpg/SQLAlchemy ya expone el código SQLSTATE vía `exc.orig.sqlstate` y el nombre de restricción vía `exc.orig.constraint_name` en `asyncpg.exceptions.UniqueViolationError`.
- Dos rutas del servicio de memoria devuelven `ProfileBlock(available=False)` desde un `except Exception` amplio: la construcción perezosa tras commit (`service.py:1189`, dentro de `get_profile`/contexto) y la reconstrucción de claves tras una mutación (`service.py:1506`, en `_rebuild_profiles_for_keys` / `_rebuild_profiles_for_memory`). Ambas tragan cualquier excepción, incluidos errores de conexión o de rol PostgreSQL, y el cliente ve "sin perfil".

## Goals / Non-Goals

**Goals:**

- La colisión de dedup se clasifica por SQLSTATE `23505` + `constraint_name`, no por texto libre.
- La ausencia legítima de perfil sigue devolviendo `available=False`; el fallo de infraestructura no.
- Cero cambios en la superficie MCP: las herramientas y sus esquemas intactos.

**Non-Goals:**

- No se reestructura el módulo de errores (`mcp/errors.py`, ADR 0012): el traductor sigue recibiendo excepciones y devolviendo la forma segura; lo que cambia es qué llega como excepción en lugar de quedarse tragado.
- No se cambia la semántica del aviso `_similar_to` ni del ciclo de reconfirmación: el aviso de similares sigue fail-open (una causa distinta a infraestructura puede degradar a "sin perfil" según la spec).
- No se renombra el índice físico `uq_memories_active_dedup`.

## Decisions

1. **SQLSTATE como clasificador primario.** `IntegrityError.orig.sqlstate == "23505"` identifica una violación de unicidad en PostgreSQL de forma estable entre versiones y drivers; el nombre de restricción (`orig.constraint_name`) desempata entre la dedup y cualquier otra restricción única futura. Se conserva un fallback a `constraint_name` cuando `sqlstate` no está disponible (drivers alternativos), pero se elimina el fallback a texto libre. Alternativa considerada: mantener el texto como último recurso — rechazada, es exactamente la fragilidad que motiva el cambio.

2. **Distinguir por tipo de error, no por mensaje.** Las rutas que hoy tragan `except Exception` se dividen: los errores de infraestructura de base de datos (`SQLAlchemyError` operacional, `OSError` de conexión) se registran con `logger.exc_info` y se propagan para que la superficie MCP los traduzca; las causas legítimas de degradación (`EmbeddingError`, ausencia de filas) conservan `available=False`. Esto respeta el ADR 0012 (el traductor MCP permanece) pero alimenta su entrada con información correcta.

3. **Log estructurado en el punto de captura.** Al dejar de tragar, el log que registra el fallo incluye el contexto de la operación (lectura vs. reconstrucción) sin exponer contenido de memoria. Reutiliza `record_sanitized_failure` de `diagnostics.py` en lugar de introducir un nuevo helper.

## Risks / Trade-offs

- **Cambio de comportamiento observable ante fallos de DB**: un cliente que hoy recibe `available=False` durante una caída de PostgreSQL pasará a recibir un error MCP traducido. Es el comportamiento correcto y el contrato de errores ya lo contempla, pero es un cambio perceptible durante una ventana de fallo.
- **Dependencia del driver**: la clasificación por SQLSTATE asume asyncpg/SQLAlchemy. Si alguna vez se soporta otro driver, el fallback por `constraint_name` sigue funcionando, pero habrá que verificarlo entonces.
- **Cobertura de tests**: la ruta de "otro IntegrityError no se reintenta" necesita un fake o integración que fuerce una violación distinta a la dedup; con stub puro no se puede sin instrumentar el driver.
