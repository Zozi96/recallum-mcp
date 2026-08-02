## Why

Recallum carga contexto al iniciar o reanudar una sesión y guía la captura al finalizar, pero no define cuándo un agente debe volver a consultar memoria mientras una tarea evoluciona. Esto deja sin cubrir los cambios internos de objetivo, subsistema, hipótesis o decisión, que los hooks y la telemetría sin contenido no pueden detectar de forma fiable.

## What Changes

- Incorporar en la skill `recallum-memory` una política de checkpoints semánticos basada en cambios materiales de la clave de recuperación de la tarea: proyecto, objetivo activo y subsistema, hipótesis o decisión actual.
- Exigir consultas `recall` enfocadas en el delta de la tarea, escritas en inglés, con un presupuesto inicial de tres resultados y evitando consultas semánticamente equivalentes durante la misma tarea.
- Distinguir los casos que requieren recuperación adicional de los que ya quedan cubiertos por el contexto inicial o por el digest de `SessionStart` en `resume|clear|compact`.
- Añadir pruebas contractuales de la guía del plugin para conservar los disparadores, límites, exclusiones y reglas de verificación en Codex, Claude Code y Grok Build.
- Añadir una evaluación reproducible del flujo del agente que compare la política actual con los checkpoints y mida recuperación oportuna, aplicación de restricciones, llamadas innecesarias, repetición y coste de contexto.
- Mantener fuera de alcance los cambios al API MCP, al ranking, a los hooks y al esquema de telemetría hasta que la evaluación demuestre una necesidad concreta.

## Capabilities

### New Capabilities

- `agent-task-memory-checkpoints`: Define cuándo y cómo un agente recupera memoria adicional durante una tarea y cómo se evalúa que esa política mejora decisiones sin generar llamadas o contexto innecesarios.

### Modified Capabilities

Ninguna.

## Impact

- Afecta principalmente `plugins/recallum-memory/skills/recallum-memory/SKILL.md` y las pruebas contractuales del plugin.
- Añade fixtures y un runner de evaluación de flujo separados del dataset de calidad de ranking existente.
- No cambia las firmas de las herramientas MCP, la persistencia, el ranking, la telemetría ni los hooks del plugin.
- La guía debe conservar el mismo comportamiento en Codex, Claude Code y Grok Build y seguir fallando de forma abierta cuando Recallum no está disponible.
