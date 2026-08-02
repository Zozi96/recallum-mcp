## 1. Infraestructura de evaluación de flujo

- [x] 1.1 Definir un dataset JSON versionado de escenarios sintéticos con corpus identificado, contexto inicial, fases, pivote opcional, memorias críticas, checkpoints esperados y criterios observables de aplicación; incluir al menos un pivote relevante, una tarea sin pivote y una ejecución con resultados repetidos.
- [x] 1.2 Implementar un evaluador sin dependencia de proveedor LLM que valide registros JSON acotados y calcule por política recuperación crítica antes de decidir, aplicación correcta, checkpoints innecesarios, exposiciones repetidas, llamadas y caracteres servidos.
- [x] 1.3 Añadir pruebas unitarias para validación del dataset y registros, cálculo de cada métrica, comparación entre políticas, reportes vacíos o incompletos y rechazo de campos de contenido o razonamiento no permitidos.

## 2. Política de checkpoints en el plugin

- [x] 2.1 Actualizar la descripción y el workflow de `plugins/recallum-memory/skills/recallum-memory/SKILL.md` con la clave de recuperación conceptual, disparadores positivos y negativos, consulta inglesa del delta con `project` y `limit=3`, filtros sólo inequívocos y continuidad fail-open.
- [x] 2.2 Documentar en la skill la supresión efímera de consultas equivalentes y resultados ya vistos, el comportamiento ante checkpoints sin resultados y la distinción entre digest genérico y snapshot enfocado después de `resume|clear|compact`.
- [x] 2.3 Mantener explícita la reconciliación de cada memoria aplicable con instrucciones y evidencia actuales, incluyendo el tratamiento existente de memorias stale, contradictorias o truncadas.
- [x] 2.4 Ampliar las pruebas contractuales del plugin para fijar los disparadores y no-disparadores, `limit=3`, idioma de consulta, identificadores verbatim, deduplicación durante la tarea, comportamiento tras compactación y equivalencia de la guía en Codex, Claude Code y Grok Build.

## 3. Validación comparativa y documentación

- [x] 3.1 Capturar registros comparables de la política vigente y de la política con checkpoints usando exactamente los mismos escenarios sintéticos, sin prompts, razonamiento, credenciales ni contenido completo en los registros versionados.
- [x] 3.2 Ejecutar el evaluador sobre ambas políticas, revisar los misses y documentar recuperación crítica, aplicación correcta, llamadas innecesarias, repetición y coste; no considerar el aumento de llamadas como señal de éxito.
- [x] 3.3 Ajustar la redacción de la skill si la comparación revela checkpoints omitidos o redundantes, conservando el alcance sin cambios de API, hooks, ranking ni telemetría.
- [x] 3.4 Documentar en el README del plugin cómo ejecutar y extender la evaluación de flujo y aclarar su diferencia respecto a MRR y recall@k de `recallum-admin eval`.

## 4. Verificación

- [x] 4.1 Ejecutar las pruebas del plugin y las pruebas unitarias del evaluador mediante el helper de salida acotada del repositorio.
- [x] 4.2 Ejecutar Ruff sobre los archivos Python modificados y validar que el código del hook conserva compatibilidad con Python 3.9.
- [x] 4.3 Ejecutar `openspec validate add-mid-task-retrieval-checkpoints --strict` y resolver cualquier incumplimiento antes de dar el cambio por implementado.
