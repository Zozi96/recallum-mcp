## 1. Guía visible del ciclo de memoria

- [x] 1.1 Añadir en `_session_context` un sufijo común y compacto que describa el checkpoint semántico con el nombre de `recall` del cliente, proyecto canónico, consulta inglesa del delta, `limit=3` y supresión cuando el contexto activo sea suficiente.
- [x] 1.2 Aplicar el mismo sufijo a las ramas con digest, sin memorias y fail-open sin duplicar la política completa de la skill ni alterar la guía existente de inicio y captura final.
- [x] 1.3 Ampliar las pruebas contractuales del hook para fijar el ciclo inicio-pivote-cierre, la ausencia de `context` redundante con digest suficiente y los nombres o mecanismos de descubrimiento de Codex, Claude Code y Grok Build.

## 2. Procedencia y repeticiones en el evaluador

- [x] 2.1 Extender de forma compatible la validación de ejecuciones con procedencia, cliente, versión declarada y estado de finalización opcionales, manteniendo válido el dataset fixture actual.
- [x] 2.2 Permitir repeticiones con `run_id` único para una misma combinación de cliente, política y escenario y rechazar únicamente ids duplicados o metadatos fuera del contrato acotado.
- [x] 2.3 Agrupar la comparación por procedencia, cliente y política e informar cobertura, ejecuciones incompletas, recuperación crítica, aplicación, llamadas innecesarias, repetición y promedios de llamadas y caracteres sobre todas las repeticiones.
- [x] 2.4 Añadir pruebas unitarias para compatibilidad exacta del informe fixture, repeticiones, clientes múltiples, procedencia mixta, ejecuciones incompletas y rechazo de campos de prompt, consulta, razonamiento, credenciales o contenido.

## 3. Probe y runner observables

- [x] 3.1 Crear fixtures ejecutables para los tres escenarios actuales con prompt sintético, workspace mínimo, reglas deterministas de recuperación y checks objetivos que produzcan las claves de criterio existentes.
- [x] 3.2 Implementar un probe MCP local enlazado sólo a loopback, protegido por token efímero, que sirva `context` y `recall` deterministas, clasifique consultas sintéticas en memoria y registre únicamente fases, herramientas, claves retornadas y caracteres servidos.
- [x] 3.3 Implementar el runner opt-in con selección de escenario, cliente, política, repeticiones y comando argv después de `--`; usar workspace temporal, variables de entorno acotadas, timeout, finalización garantizada del probe y limpieza en éxito o fallo.
- [x] 3.4 Ejecutar los checks objetivos después del agente, convertir llamadas y resultados en ejecuciones compatibles con el evaluador y marcar como omitidas o incompletas las sesiones que no arrancan, no conectan o exceden el timeout sin fabricar eventos.
- [x] 3.5 Añadir un agente falso de prueba y cubrir captura exitosa tras pivote, recall redundante, ausencia de checkpoint, fallo del verificador, timeout, limpieza, aislamiento del token y exclusión de `stdout`, `stderr` y texto de consultas del dataset.

## 4. Documentación y verificación

- [x] 4.1 Documentar en el README del plugin el contrato de variables de entorno, ejemplos de configuración temporal para Codex, Claude Code y Grok Build, la recomendación de tres repeticiones y la diferencia entre fixtures, ejecuciones observadas, ranking y telemetría.
- [x] 4.2 Ejecutar las pruebas del plugin y del evaluador, las pruebas de integración del runner con el agente falso y Ruff sobre los archivos Python modificados mediante el helper de salida acotada del repositorio.
- [x] 4.3 Verificar que el hook conserva compatibilidad con Python 3.9, que ninguna prueba requiere red ni un cliente comercial y que el runner no modifica configuración persistente del usuario.
- [x] 4.4 Ejecutar `openspec validate improve-coding-agent-recall-adherence --strict` y resolver cualquier incumplimiento antes de iniciar una matriz opt-in con agentes reales.
