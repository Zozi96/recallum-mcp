## 1. Cola en memoria de claves pendientes

- [x] 1.1 Crear un componente de cola acotada para claves de perfil `(user_id, project|None)` con coalescencia por clave, siguiendo el patrón de ciclo de vida de `TelemetryBuffer` (arranque/parada/`stop` drena). Verificación: tests unitarios del componente cubriendo coalescencia, acotación y drenado en `stop`.
- [x] 1.2 Cablear el componente en `recallum/container.py` y `recallum/app.py` con arranque en lifespan y parada ordenada. Verificación: tests de ciclo de vida de la app en `tests/unit/test_app.py` pasan con el trabajador activo.

## 2. Mutaciones encolan en lugar de reconstruir en línea

- [x] 2.1 En `MemoryService`, sustituir la llamada `_rebuild_profiles_for_memory` posterior al commit por un encolado de las claves afectadas (misma selección de claves que hoy: clave global; para memorias globales, también los proyectos del usuario). Escribir primero el test que falle: `remember` debe devolver sin invocar la reconstrucción en la misma llamada. Verificación: `tests/unit/test_memory_profile.py` y `tests/unit/test_service.py` actualizados pasan.
- [x] 2.2 Aplicar el mismo cambio en `update`, `merge_memories`, `reconfirm` y `forget`. Verificación: ningún test de escritura observa la reconstrucción síncrona; todos verdes.
- [x] 2.3 Mantener el requisito `Fallo de rebuild no revierte el remember`: el trabajador registra y descarta fallos de reconstrucción sin propagarlos a la mutación ya confirmada. Verificación: test con reconstrucción fallida en el trabajador; la memoria permanece y el error sólo aparece en log.

## 3. Trabajador de drenado

- [x] 3.1 El trabajador drena claves en lotes y llama a `_rebuild_profiles_for_keys` existente (sin reescribir su lógica interna). Verificación: test de integración del trabajador con base real si está disponible (`tests/integration`), o unitario con repositorio fake.
- [x] 3.2 Confirmar que la lectura perezosa sigue reconstruyendo cuando la generación difiere aunque el trabajador no haya corrido todavía. Verificación: test de `get_profile`/`context` con clave pendiente encolada pero sin trabajador; la respuesta refleja la mutación.

## 4. Validación global

- [x] 4.1 Ejecutar `uv run pytest tests/unit -q` completo y corregir regresiones. Verificación: suite unitaria verde.
- [x] 4.2 Si hay PostgreSQL disponible, ejecutar la integración relevante. Verificación: `tests/integration` verde o marcado según su marker. Resultado: 124/125 verdes tras alinear `test_remember_batch_shares_one_transaction` al comportamiento diferido (la aserción pre-cambio esperaba el rebuild inline síncrono que esta change elimina deliberadamente).
