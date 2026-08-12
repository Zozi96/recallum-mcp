## ADDED Requirements

### Requirement: Guía de vecinos, reconfirmación y prompts
La skill y el recordatorio de `SessionStart` MUST enseñar el ciclo ampliado: tras un acierto útil de `recall` o `context`, la guía MUST presentar `related_memories` como paso opcional sólo cuando haga falta el entorno temático de una semilla, no en cada recuperación; ante la cola de memorias obsoletas MUST preferir `reconfirm` frente a volver a guardar el mismo contenido; y, si el cliente soporta prompts MCP, MUST nombrar `session-start`, `capture-scan` y `stale-review` como atajos del ciclo ya documentado.

#### Scenario: Vecindario opcional
- **WHEN** un `recall` o `context` devuelve una memoria útil y el agente necesita explorar el tema
- **THEN** la guía vigente menciona `related_memories` como paso opcional, no obligatorio en cada recuperación

#### Scenario: Cola obsoleta
- **WHEN** el agente verifica una memoria marcada como stale que sigue siendo cierta
- **THEN** la guía vigente indica `reconfirm` en lugar de un `remember` idéntico

#### Scenario: Prompts como atajo
- **WHEN** el cliente expone prompts MCP
- **THEN** la guía vigente nombra `session-start`, `capture-scan` y `stale-review` como atajos del ciclo start → captura → revisión stale
