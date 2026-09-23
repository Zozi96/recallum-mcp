## Context

Ver `proposal.md` para la motivación. La propuesta cubre cuatro mejoras y sólo produce planificación en esta fase.

- `recallum/memory/profile_select.py:48` admite static por categoría **o** importancia. La selección SQL acotada también usa ese criterio en `recallum/db/repositories/memory_repo.py`; cambiar sólo el helper dejaría preferencias fuera de los candidatos ya limitados.
- `MemoryService.context` reserva y descuenta el perfil antes de empaquetar candidatos de foco. Los límites, el snapshot con RLS, la deduplicación y los contadores ya existen; no hace falta un segundo recuperador.
- `recallum/mcp/server.py:160` publica `INSTRUCTIONS` una vez como instrucciones del servidor. En esta sesión el cliente las presentó repetidas junto a cada herramienta; no está demostrado que el servidor duplique el texto dentro de `tools/list`. Los límites se medirán sobre ambas superficies controladas por Recallum por separado.
- `recallum/mcp/errors.py` ya centraliza errores de herramientas y recursos. `diagnostic_correlation` y `record_sanitized_failure` permiten correlacionar sin imprimir texto de excepciones.
- Las specs vigentes permiten hechos importantes en static y protegen todo el perfil frente a focus. Los deltas sustituyen expresamente esas reglas; no son una corrección invisible ni una promesa de relevancia perfecta.

## Goals / Non-Goals

**Goals:** reutilizar categorías, ranking, presupuestos, esquemas, prompts y diagnóstico existentes; hacer verificables las cuatro mejoras con corpus sintético, descubrimiento MCP y comprobaciones del plugin.

**Non-Goals:** fijación manual de memorias, clasificación con LLM, umbral semántico nuevo, traducción del servidor, cambios en índices/embeddings, corrección de memorias mal clasificadas o mal asignadas a proyectos, nueva herramienta de diagnóstico, ajustes de clientes instalados o interfaz web.

## Decisions

### 1. Static sólo para preferencias y restricciones; foco sin dynamic reservado

Usar las categorías existentes como aproximación explícita a reglas permanentes. Mantener el orden por importancia y desempates actuales entre candidatos elegibles. Actualizar tanto los predicados SQL antes de `LIMIT` como la selección pura y sus llamadores. Conservar temporalmente `profile_static_min_importance` como ajuste aceptado, documentado como obsoleto y sin efecto sobre static; no añadir un ajuste sustituto ni rechazar configuraciones existentes.

Para `context` con foco normalizado no vacío, vaciar dynamic **antes** de aplicar el presupuesto de perfil, recalcular `source_memory_ids` y el digest sobre los ítems servidos, y permitir que los mismos recuerdos participen en los pools ordinarios. Aplicar la misma regla a las rutas caliente y de reconstrucción. Conservar `built_at` como fecha de materialización de static. No crear otra consulta de `recall` ni registrar uso para candidatos descartados. `focus=None`, `""` y espacios conservan dynamic por recencia; el recurso de perfil también lo conserva.

Se mantiene el orden de categorías y la prioridad de foco dentro de cada categoría. Si las reglas static o categorías anteriores consumen el presupuesto, no se garantiza un resultado de foco. La prueba de mejora usa un corpus controlado: una restricción, un hecho reciente ajeno sin coincidencia y un hecho pertinente de la misma categoría, dos plazas y caracteres suficientes. Deben salir la restricción y el hecho pertinente, también en degradación textual.

Alternativas descartadas: marcar manualmente memorias fijadas exigiría nuevo estado y mantenimiento; filtrar dynamic por similitud introduciría otra política de ranking. Vaciarlo sólo cuando ya hay una tarea explícita permite que la recuperación existente decida sin esas extensiones.

### 2. Descripciones breves sin depender de que el cliente muestre la guía común

Mantener `INSTRUCTIONS` como entrada compartida y los docstrings como descripciones por herramienta. Establecer límites de 1.400 caracteres Unicode para instrucciones y 1.600 para cada descripción anunciada. Los 15 nombres y esquemas permanecen iguales. Cada descripción debe tener propósito, cuándo elegirla y un ejemplo mínimo válido; las operaciones que escriben contenido retienen la advertencia sobre información sensible localmente.

Revisar **15/15**: `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm`, `forget`, `save_skill`, `match_skills`, `get_skill`, `forget_skill`. Comprobar además: `similar` y contradicciones en captura/fusión; reemplazo explícito de skills; memorias frente a procedimientos; truncado y omisiones en lecturas; ámbito, anclas y degradación textual en búsqueda; significado y resultado de borrado lógico; ausencia de filtraciones de propiedad.

Mantener el ciclo detallado en la skill/regla y los tres prompts existentes. Medir la longitud recibida en `initialize.instructions` y `tools/list`, no sólo literales del archivo. Registrar antes/después y, por separado, la suma estimada si un cliente antepone instrucciones a cada herramienta; no presentar esa suma como tokens reales o latencia medida.

Alternativas descartadas: añadir herramientas de ayuda o nuevos prompts aumenta la elección; eliminar toda repetición local de seguridad deja clientes sin instrucciones compartidas insuficientemente guiados.

### 3. Ejemplos de búsqueda en las superficies distribuidas

Editar `plugins/recallum-memory/skills/recallum-memory/SKILL.md`, `plugins/recallum-memory/rules/recallum-memory.mdc` y `docs/clients.md`; mantener breve la descripción de `recall` en el servidor. Reutilizar las reglas de idioma ya existentes. No añadir llamadas al hook de inicio: se verifica su compatibilidad con la guía de checkpoint actual.

Los ejemplos usan P para representar la clave canónica obtenida por el hook, nunca una clave real de este workspace que pueda copiarse a otro proyecto. La guía explica que estos son argumentos de herramientas MCP, no una nueva API Python:

| Intención | Argumentos mínimos ilustrativos |
| --- | --- |
| Proyecto con globales | `recall(query="Context budget decisions", project=P, limit=3)` |
| Sólo proyecto | `recall(query="Context budget decisions", project=P, scope="project", limit=3)` |
| Sólo globales | `recall(query="Preferred coding conventions", scope="global", limit=3)` |
| Símbolo anclado | `recall(query="Context budget decisions", project=P, symbol="MemoryService.context", limit=3)` |
| Archivo anclado | `recall(query="Context budget decisions", project=P, file="recallum/memory/service.py", limit=3)` |
| Mención sin ancla | `recall(query="Decisions about MemoryService.context", project=P, limit=3)` |
| Memoria conocida | `get_memory(memory_id=M)` con M como UUID de memoria obtenido previamente |

El filtro de ancla vacío no demuestra ausencia de menciones textuales. Mostrar la consulta sin ese filtro como opción cuando sea pertinente, no como segunda llamada obligatoria. Traducir «¿qué decidimos sobre MemoryService.context?» a `What did we decide about MemoryService.context?`; conservar rutas, comandos y términos definidos por el usuario. No convertir automáticamente memorias existentes ni introducir servicios de traducción.

Alternativa descartada: autodetectar idioma y traducir en el servidor agrega dependencias y comportamiento no solicitado. La mejora pedida es orientación utilizable por el agente.

### 4. Referencia de error aleatoria en la frontera existente

Generar una referencia `mcp-` más `uuid.uuid4().hex` por invocación del decorador existente, y vincularla mediante `diagnostic_correlation` durante la llamada. Reemplazar el hash del identificador MCP controlado por el cliente; no añadir otro almacén, header ni endpoint. En excepciones inesperadas, usar esa referencia en el registro sanitizado y en `internal server error (reference: <ref>)`. Mantener los mensajes esperados y la degradación sin cambios.

Aplicar a herramientas y a los dos recursos de perfil que comparten el decorador. Conservar la elevación de `ToolError` fuera del bloque de excepción para no retener `__cause__`/`__context__` sensibles. Probar invocaciones concurrentes y secuenciales con IDs de cliente repetidos y con sentinels; cada respuesta debe corresponder a su log sin reflejar esos IDs. El request ID de HTTP conserva su contrato independiente. Documentar en `docs/operations.md` cómo buscar la referencia en logs ya restringidos a operadores; las mutaciones que fallen inesperadamente no deben recomendarse para reintento ciego, porque su resultado puede ser incierto.

Alternativas descartadas: publicar el ID recibido o su hash puede repetir referencias entre sesiones y derivarlas de entrada sensible; devolver detalles de excepción vulnera el contrato de confidencialidad. UUID de la biblioteca estándar evita ambas cosas sin dependencias.

## Risks / Trade-offs

- Preferencias o restricciones mal clasificadas pueden seguir aportando ruido → conservar una política determinista por categoría; no prometer pertinencia perfecta ni reclasificar el corpus en esta entrega.
- Dynamic vacío pierde la recapitulación automática en contexto enfocado → mantenerla sin foco y en el recurso; los recuerdos recientes pertinentes aún compiten en los grupos.
- Una caché anterior puede seguir fijando hechos sin mutaciones nuevas → invalidar todas las filas derivadas al actualizar y comprobar la primera lectura.
- Acortar demasiado puede ocultar advertencias o cambiar selección de herramientas → revisar las quince descripciones con ejemplos válidos y una matriz de salvaguardas; no aceptar sólo una comprobación de tamaño.
- Clientes que comparan literalmente `internal server error` deben adaptarse → documentar el nuevo formato; los errores esperados y esquemas de éxito no cambian.
- La calidad real de recuperación y el ahorro de tokens dependen del corpus y cliente → publicar resultados sintéticos y medidas de caracteres con sus límites, sin inferir mejoras universales.

## Migration Plan

1. Añadir una migración Alembic de datos que marque `memory_profiles.generation=-1` en **todas** las filas derivadas. Seguir el precedente de `0013_admin_memory_aggregates.py`: en la transacción de migración del propietario, quitar temporalmente FORCE RLS sólo de `memory_profiles`, ejecutar la actualización y restaurar FORCE RLS antes del commit. No deshabilitar RLS en memorias fuente ni conceder BYPASSRLS al rol de aplicación. Un error debe revertir la transacción completa.
2. Coordinar una actualización con procesos y trabajadores antiguos detenidos: ejecutar la migración y arrancar la nueva versión. Esto evita que un proceso antiguo reconstruya una caché válida con la política anterior entre migración y arranque. No se promete despliegue mixto sin interrupción.
3. Comprobar primera lectura, reconstrucción perezosa, aislamiento y flags RLS con el rol no superusuario de integración. Comparar todas las columnas de memorias fuente antes/después; también contadores y contenido de skills deben permanecer intactos.
4. Distribuir el plugin mediante el mecanismo de publicación existente en una entrega posterior autorizada; documentar el ajuste static obsoleto y el formato de error nuevo.
5. Para rollback, detener la versión nueva, ejecutar el downgrade que vuelve a invalidar las filas derivadas y arrancar la versión anterior. La política anterior se recupera por reconstrucción; no hay que restaurar memorias fuente ni deshacer cambios de esquema.

## Validation Strategy

- Política de perfil y foco → verificar: escenarios de las dos specs con corpus sintético, ruta caliente/fría, presupuestos, deduplicación, conteos, hash, ausencia de uso para descartados, cero coincidencias, foco vacío y Ollama indisponible.
- Descripciones y búsqueda → verificar: las 15 herramientas por el transporte MCP, límites de caracteres, esquemas sin cambios, ejemplos válidos y salvaguardas semánticas; matriz de scopes/anclas con propietario, otro proyecto y otro usuario.
- Errores → verificar: texto genérico con referencia coincidente en logs, unicidad por invocación, recursos, concurrencia, ausencia de sentinels en respuesta/logs/cadena de excepción y mensajes esperados intactos.
- Migración y distribución → verificar: upgrade/downgrade con FORCE RLS restaurado, corpus intacto, primera lectura correcta y pruebas existentes del plugin.

Durante apply, usar las suites existentes de perfil/contexto y MCP bajo `tests/unit/`, `tests/integration/test_db.py` y `plugins/recallum-memory/tests/test_plugin.py`. No añadir un framework. La revisión previa de esta sesión no pudo ejecutar pytest por falta del ejecutable; eso no es un resultado de pruebas. Esta propuesta se valida con OpenSpec y revisión de documentos; las comprobaciones de comportamiento quedan pendientes para apply.
