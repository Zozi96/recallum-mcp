## Why

El ciclo start → checkpoint → capture y el benchmark opt-in ya existen, pero la adherencia real de Cursor, Codex, Claude Code y Grok Build sigue siendo la apuesta de producto sin un ritmo operativo ni una matriz mínima de evidencia. Sin eso, el resto de mejoras (ranking, grafo) optimizan sin saber si los agentes usan la memoria.

## What Changes

- Definir una matriz mínima de clientes y políticas que el operador puede ejecutar con el benchmark observado existente.
- Exigir un runbook operativo (cómo lanzar, qué contar como evidencia, cómo interpretar omisiones/incompletas) sin telemetría de producción ni contenido de usuario.
- Ampliar escenarios sintéticos sólo donde falte cobertura de pivotes o captura final, reutilizando el evaluador vigente.
- Mantener fuera de alcance: API MCP de producción, ranking, `recall_usage_weight`, persistencia de memorias, telemetría de servidor y estado de sesión.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-task-memory-checkpoints`: Operación repetible del benchmark observado, matriz mínima de clientes/políticas y runbook de evidencia.
- `agent-session-bootstrap`: La guía de ciclo de memoria MUST permanecer alineada con los nombres y fallos fail-open que el benchmark asume por cliente.

## Impact

- Afecta `scripts/agent_workflow_benchmark.py`, fixtures/escenarios de workflow, documentación del plugin y posiblemente hooks sólo si el runbook exige equivalencia contractual.
- No cambia herramientas MCP, respuestas de producción, base de datos ni ranking.
