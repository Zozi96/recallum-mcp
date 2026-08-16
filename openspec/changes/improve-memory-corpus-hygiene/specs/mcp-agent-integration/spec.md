## MODIFIED Requirements

### Requirement: Prompts MCP del ciclo de memoria
El servidor MCP MUST publicar exactamente tres prompts allowlisteados: `session-start`, `capture-scan` y `stale-review`. `session-start` MUST orientar bootstrap con `context` (proyecto y foco cuando la tarea se conoce). `capture-scan` MUST orientar captura final atómica en inglés vía `remember_batch`, sin secretos ni recaps, y MUST recordar leer `similar` y reconciliar (merge vs update) antes de dar por cerrada la captura. `stale-review` MUST orientar enumerar `list_memories(stale=true)` y resolver cada ítem verificado con `get_memory` más exactamente uno de `reconfirm`, `update`, `forget` o `merge_memories`.

#### Scenario: Descubrimiento de prompts
- **WHEN** un cliente autenticado lista los prompts MCP
- **THEN** aparecen únicamente `session-start`, `capture-scan` y `stale-review`

#### Scenario: Prompt no allowlisteado
- **WHEN** el servidor registra un prompt con un nombre distinto de esos tres
- **THEN** la validación de arranque falla antes de servir tráfico

#### Scenario: session-start
- **WHEN** un cliente obtiene el prompt `session-start`
- **THEN** la guía indica llamar `context` con proyecto y, cuando la tarea se conoce, foco

#### Scenario: capture-scan
- **WHEN** un cliente obtiene el prompt `capture-scan`
- **THEN** la guía indica captura atómica en inglés vía `remember_batch` y reconciliar `similar` sin auto-resolver contradicciones

#### Scenario: stale-review
- **WHEN** un cliente obtiene el prompt `stale-review`
- **THEN** la guía indica enumerar la cola stale y cerrar cada ítem verificado con `reconfirm`, `update`, `forget` o `merge_memories`
