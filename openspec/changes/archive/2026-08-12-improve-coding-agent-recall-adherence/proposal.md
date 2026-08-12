## Why

Recallum ya define checkpoints semánticos y sus trazas sintéticas muestran mejor recuperación con menos llamadas redundantes, pero el recordatorio universal de `SessionStart` sólo hace explícitos el inicio y la captura final. Además, las ejecuciones evaluadas hoy están escritas a mano, así que todavía no demuestran que Codex, Claude Code o Grok Build sigan la política durante tareas reales.

## What Changes

- Hacer visible en todas las variantes de `SessionStart` un ciclo compacto de tres momentos: cargar contexto al comenzar, ejecutar un único `recall` ante un cambio material de subsistema, hipótesis o decisión, y capturar contexto durable verificado al finalizar.
- Mantener la skill completa como autoridad para los detalles y conservar en el recordatorio breve `project`, consulta inglesa del delta, `limit=3`, supresión cuando el contexto ya cubre la decisión y continuidad fail-open.
- Añadir un benchmark controlado que reutilice el evaluador de flujo vigente y ejecute agentes reales contra escenarios sintéticos y un probe MCP local, sin depender de telemetría de producción.
- Verificar la aplicación de cada memoria mediante checks objetivos del escenario, registrar sólo eventos acotados y repetir ejecuciones etiquetadas por cliente y política para distinguir adherencia de un resultado aislado.
- Ampliar las pruebas contractuales y la documentación para que la guía breve, la captura segura y el informe comparativo permanezcan equivalentes entre Codex, Claude Code y Grok Build.
- Mantener fuera de alcance cambios al API MCP de producción, ranking, persistencia, telemetría, estado de sesión del servidor o `recall_usage_weight`.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-session-bootstrap`: El contexto inyectado al iniciar o reanudar sesión expone directamente el checkpoint semántico entre la carga inicial y la captura final.
- `agent-task-memory-checkpoints`: La evaluación reproducible incorpora ejecuciones observadas de agentes reales, checks objetivos y comparación repetida por cliente y política.

## Impact

- Afecta `plugins/recallum-memory/hooks/recallum_hook.py`, sus pruebas contractuales y la documentación del plugin.
- Extiende `recallum/workflow_evaluation.py`, los scripts y fixtures de evaluación, reutilizando el esquema y las métricas existentes siempre que sea posible.
- El benchmark usa escenarios sintéticos y un probe local; no almacena prompts, razonamiento, credenciales ni contenido de usuario.
- No cambia herramientas MCP, respuestas de producción, base de datos, telemetría desplegada ni dependencias de runtime del servidor.
