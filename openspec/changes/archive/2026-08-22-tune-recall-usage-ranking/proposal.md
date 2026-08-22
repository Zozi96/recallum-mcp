## Why

`recall_count` / uso en context ya se registran, pero `recall_usage_weight` permanece en 0.0 a propósito. Sin un dataset de ranking medible y un experimento controlado, encender ese peso sería un rich-get-richer a ciegas. Hay harness de evaluación; falta el contrato de cuándo y cómo la señal de uso puede participar en la fusión.

## What Changes

- Exigir un dataset versionado de ranking (consultas → memorias esperadas) separado del evaluador de flujo de checkpoints.
- Definir que la fusión de `recall` MAY incorporar un voto de uso configurable, con default 0.0 hasta que un experimento documentado justifique un peso > 0.
- Exigir que cualquier peso de uso no-cero se active sólo tras comparación MRR/recall@k (y misses) frente al baseline, sin romper degradación textual ni aislamiento.
- Mantener fuera de alcance: cambios al ciclo de adherencia del agente, telemetría con contenido, grafo y auto-higiene del corpus.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-retrieval`: Fusión de ranking con voto de uso opcional, default seguro, y evaluación reproducible de ranking distinta del flujo de checkpoints.

## Impact

- Afecta `recallum/memory/limits.py`, fusión en `MemoryService.recall`, `recallum/evaluation.py`, datasets/scripts de eval y documentación de tunables.
- No cambia esquemas MCP públicos salvo campos ya expuestos de uso; no cambia identidad ni RLS.
