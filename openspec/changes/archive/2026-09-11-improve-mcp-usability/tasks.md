## 1. Preparar comprobaciones y línea base

- [x] 1.1 Preparar el entorno de desarrollo existente con `uv sync --group dev` y comprobar que `uv run pytest --version` funciona; ejecutar las pruebas actuales de perfil/contexto y MCP indicadas en design.md y registrar cualquier fallo previo antes de editar código.
- [x] 1.2 Registrar por transporte MCP los quince nombres, esquemas, longitud de `initialize.instructions` y de cada descripción; verificar que la línea base enumera 15/15 y separa caracteres reales de la estimación para clientes que repiten instrucciones.

## 2. Hacer el perfil y el contexto pertinentes a la tarea

- [x] 2.1 Añadir casos de aceptación a `tests/unit/test_profile_select.py`, `tests/unit/test_memory_profile.py` y `tests/unit/test_context_budget.py` para static sólo preference/constraint y dynamic vacío con foco; verificar que los casos nuevos fallan por el comportamiento anterior, incluyendo el corpus de dos plazas definido en la spec.
- [x] 2.2 Cambiar elegibilidad en la selección pura y en todos los predicados SQL de candidatos static antes de sus límites; mantener `profile_static_min_importance` aceptado como obsoleto y sin efecto; verificar los casos de hechos/decisiones de máxima importancia y una restricción de baja importancia que cabe en static, incluso con más hechos que el límite SQL.
- [x] 2.3 Vaciar dynamic en las rutas caliente y fría de `context` con foco no vacío antes de presupuestar y recalcular IDs/digest; verificar foco ausente/vacío/espacios, candidatos recientes pertinentes aún recuperables, presupuesto agotado por static, cero coincidencias, degradación textual, deduplicación, omisiones por categoría, `built_at` y registro de uso sólo para ítems servidos.
- [x] 2.4 Añadir la migración de invalidación de todas las filas de `memory_profiles` mediante `generation=-1`, con restauración transaccional de FORCE RLS tanto en upgrade como downgrade; verificar con dos propietarios y varias claves globales/de proyecto que no quedan filas de generación anterior válidas, que las memorias y skills fuente permanecen idénticas y que un fallo de migración revierte los cambios y los flags RLS.
- [x] 2.5 Extender `tests/integration/test_db.py` para primera lectura tras upgrade/downgrade, aislamiento, snapshot y recuperación textual del corpus acotado; verificar las cuatro combinaciones de perfil vigente/reconstruido y contexto con/sin foco, sin alterar la regla de que recall no invalida static.

## 3. Simplificar las quince descripciones MCP

- [x] 3.1 Reducir `INSTRUCTIONS` y las descripciones de `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm`, `forget`, `save_skill`, `match_skills`, `get_skill` y `forget_skill`; verificar límites de 1.400/1.600 caracteres sobre lo anunciado por MCP y propósito, elección y ejemplo válido en las 15/15.
- [x] 3.2 Ampliar las comprobaciones existentes de herramientas/documentación para validar los quince ejemplos y conservar nombres y esquemas de entrada/salida frente a la línea base; verificar también que siguen existiendo exactamente los tres prompts y los recursos de perfil previos.
- [x] 3.3 Revisar cada descripción aislada de la guía compartida contra la matriz de salvaguardas de design.md: contenido sensible, similar, contradicciones, reemplazo, truncado, ámbitos, anclas, degradación y propiedad; verificar que todas las reglas aplicables sobreviven y registrar las longitudes antes/después sin afirmar ahorro de tokens no medido.

## 4. Enseñar búsquedas correctas en el plugin y documentación

- [x] 4.1 Añadir a la skill y regla de memoria distribuidas y `docs/clients.md` los siete ejemplos de design.md: proyecto con globales, sólo proyecto, sólo globales, símbolo, archivo, mención sin ancla y UUID conocido; verificar argumentos válidos, uso de la clave canónica obtenida y ausencia de claves reales copiadas de este workspace.
- [x] 4.2 Añadir el ejemplo español → inglés y la preservación literal de `MemoryService.context`, `recallum/memory/service.py` y `uv run pytest`; extender las comprobaciones contractuales en `plugins/recallum-memory/tests/test_plugin.py` y verificar `limit=3`, nombres por cliente, supresión de consultas redundantes, fail-open y ausencia de traducción en servidor o reescritura de memorias.
- [x] 4.3 Ejecutar los ejemplos contra un corpus sintético del propietario con memorias globales, de dos proyectos, ancladas y no ancladas, más datos de otro usuario; verificar cada ámbito, el rechazo de `scope='project'` sin `project` y la diferencia entre filtro de ancla vacío y mención textual, reutilizando pruebas de recuperación existentes.

## 5. Correlacionar errores sin exponer datos

- [x] 5.1 Añadir pruebas al contrato de errores MCP para formato de referencia, log coincidente, dos recursos de perfil, llamadas repetidas/concurrentes con IDs de cliente iguales y sentinels; verificar que fallan por ausencia del nuevo contrato y conservan expectativas exactas para errores de dominio y embeddings.
- [x] 5.2 Generar `mcp-` más UUID4 hexadecimal por invocación en el decorador compartido, vincularlo al diagnóstico existente y añadirlo sólo al mensaje inesperado; verificar en `tests/unit/test_mcp_errors.py` y `tests/unit/test_mcp_tools.py` la correlación, restauración del contexto, error MCP efectivo y ausencia de sentinels en respuesta, logs y cadena de excepción.
- [x] 5.3 Documentar en `docs/operations.md` el formato de referencia, búsqueda en logs de operador, ajuste static obsoleto y orden de upgrade/rollback con procesos detenidos; verificar coherencia con las pruebas de migración y que no se recomienda reintentar a ciegas una mutación cuyo resultado es incierto.

## 6. Cerrar la implementación con evidencia

- [x] 6.1 Ejecutar `uv run pytest tests/unit/test_profile_select.py tests/unit/test_memory_profile.py tests/unit/test_context_budget.py tests/unit/test_mcp_errors.py tests/unit/test_mcp_tools.py tests/unit/test_mcp_tools_docs.py tests/unit/test_fastmcp_compatibility.py` y `python3 -m unittest discover -s plugins/recallum-memory/tests -p test_plugin.py`; verificar salida exitosa y registrar las pruebas realmente ejecutadas.
- [x] 6.2 Ejecutar `uv run pytest tests/integration/test_db.py` con las dependencias de integración del repositorio, `uv run ruff check recallum tests` y `uv run mypy recallum`; verificar migración, aislamiento y contexto completo además de los checks estáticos, distinguiendo fallos previos o límites ambientales sin declararlos aprobados.
- [x] 6.3 Obtener revisión de corrección y de seguridad sobre el diff final y contrastar todas las tareas con las cuatro specs delta; verificar 4/4 mejoras, 15/15 descripciones y cero hallazgos pendientes antes de declarar implementación lista, sin publicar ni desplegar como parte implícita del apply.
