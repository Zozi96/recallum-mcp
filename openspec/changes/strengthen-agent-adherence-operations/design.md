## Context

Existen benchmark observado, evaluador de flujo y ciclo start/checkpoint/capture. Falta operación repetible: matriz mínima por cliente, runbook y evidencia que no se confunda con fixtures.

## Goals / Non-Goals

**Goals:**
- Matriz mínima documentada y ejecutable (clientes soportados × política vigente).
- Runbook sin secretos ni contenido de producción.
- Alineación contractual entre `SessionStart` y lo que el benchmark espera por cliente.

**Non-Goals:**
- Cambiar API MCP, ranking, `recall_usage_weight`, telemetría de servidor o persistencia.
- Convertir el benchmark en CI obligatorio en cada PR (sigue opt-in operativo).

## Decisions

- **Opt-in operativo, no CI blocking**: la matriz vive como procedimiento y artefactos versionados de resultados ejemplo/fixtures de escenario; CI puede validar que el harness arranca en seco, no que haya corridas reales de agentes en cada PR.
- **Reutilizar harness**: extender escenarios/docs alrededor de `scripts/agent_workflow_benchmark.py` y `workflow_evaluation.py`, no un segundo evaluador.
- **Evidencia**: sólo trazas acotadas ya permitidas por el spec de registro observado.

## Risks / Trade-offs

- [Coste de corridas reales] → Matriz mínima pequeña; repeticiones configurables.
- [Clientes no disponibles en un host] → Informe con huecos explícitos, no fallar el producto.
- [Drift guía vs benchmark] → Tarea de revisión contractual en el change.

## Migration Plan

1. Publicar runbook + matriz.
2. Ampliar escenarios si faltan pivotes.
3. Correr matriz donde haya clientes; versionar sólo trazas acotadas opt-in.

## Open Questions

- ¿Incluir Cursor en la matriz mínima del primer corte o dejarlo como extensión documentada? Default propuesto: documentarlo como soportado si el harness ya lo permite; no bloquear el change si el host no lo tiene.
