## MODIFIED Requirements

### Requirement: Guía de vecinos, reconfirmación y prompts
La skill y el recordatorio de `SessionStart` MUST enseñar el ciclo ampliado: tras un acierto útil de `recall` o `context`, la guía MUST presentar `related_memories` como paso opcional sólo cuando haga falta el entorno temático de una semilla, no en cada recuperación; ante la cola de memorias obsoletas MUST exigir un desenlace explícito (`reconfirm` / `update` / `forget` / `merge_memories`) y preferir `reconfirm` frente a volver a guardar el mismo contenido; ante `similar` MUST distinguir merge (reexpresión) de update/forget (contradicción o hecho incorrecto); y, si el cliente soporta prompts MCP, MUST nombrar `session-start`, `capture-scan` y `stale-review` como atajos del ciclo ya documentado.

#### Scenario: Vecindario opcional
- **WHEN** un `recall` o `context` devuelve una memoria útil y el agente necesita explorar el tema
- **THEN** la guía vigente menciona `related_memories` como paso opcional, no obligatorio en cada recuperación

#### Scenario: Cola obsoleta
- **WHEN** el agente verifica una memoria marcada como stale que sigue siendo cierta
- **THEN** la guía vigente indica `reconfirm` en lugar de un `remember` idéntico

#### Scenario: Cola obsoleta con desenlace
- **WHEN** el agente completa la verificación de un ítem stale
- **THEN** la guía vigente exige elegir `reconfirm`, `update`, `forget` o `merge_memories` según el resultado

#### Scenario: Similares en captura
- **WHEN** `remember` o `remember_batch` reportan similares
- **THEN** la guía vigente indica merge para reexpresiones y update/forget para contradicciones, sin auto-resolver

#### Scenario: Prompts como atajo
- **WHEN** el cliente expone prompts MCP
- **THEN** la guía vigente nombra `session-start`, `capture-scan` y `stale-review` como atajos del ciclo start → captura → revisión stale
