## 1. Clasificación de dedup por SQLSTATE

- [ ] 1.1 Reescribir `_is_dedup_integrity_error` (`recallum/memory/service.py`) para clasificar por `exc.orig.sqlstate == "23505"` y `exc.orig.constraint_name == "uq_memories_active_dedup"`, eliminando el fallback por texto libre. Escribir primero el test que falle: una violación de unicidad cuyo texto no contiene el nombre del índice debe seguir clasificándose como dedup. Verificación: nuevo caso en `tests/unit/test_service.py` pasa.
- [ ] 1.2 Añadir caso negativo: un `IntegrityError` por otra restricción no se reintenta y se propaga. Verificación: test unitario pasa y confirma que ninguna ruta lo etiqueta como reconfirmación.
- [ ] 1.3 Si hay PostgreSQL disponible, confirmar con integración que la colisión concurrente real se clasifica por SQLSTATE y no por texto. Verificación: `tests/integration/test_db.py` cubre dedup concurrente y pasa.

## 2. Perfil: infraestructura no se enmascara como ausencia

- [ ] 2.1 En las rutas que hoy tragan `except Exception` devolviendo `ProfileBlock(available=False)` (`service.py:1189` y `service.py:1506`), dividir el manejo: errores de infraestructura de base de datos propagan tras registrarse con `record_sanitized_failure`; causas legítimas (embedding, ausencia de fila) devuelven `available=False`. Escribir primero el test que falle: un fallo de DB durante la lectura del perfil hoy devuelve `available=False`; tras el cambio debe propagar. Verificación: nuevo caso en `tests/unit/test_memory_profile.py` pasa.
- [ ] 2.2 Verificar que `context`/`get_profile` sigue sirviendo `available=False` en el caso legítimo de ausencia. Verificación: los escenarios existentes de `memory-profile` (`Primera lectura sin fila`, `Degradación`) siguen verdes sin modificar.

## 3. Validación global

- [ ] 3.1 Ejecutar `uv run pytest tests/unit -q` completo. Verificación: suite unitaria verde.
- [ ] 3.2 Si hay PostgreSQL disponible, ejecutar la integración relevante. Verificación: `tests/integration` verde o marcado según su marker.
