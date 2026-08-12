## MODIFIED Requirements

### Requirement: Conjunto mínimo de herramientas
El sistema MUST publicar las capacidades de guardado individual y por lotes, recuperación, contexto con foco opcional, lectura por identificador, enumeración, corrección, consolidación, vecinos temáticos, reconfirmación y borrado mediante las herramientas `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm` y `forget`. El sistema MUST NOT publicar el grafo temático completo como herramienta MCP.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia exactamente esas once herramientas con esquemas de entrada y salida validados

#### Scenario: Contexto con foco
- **WHEN** un cliente inspecciona el esquema de `context`
- **THEN** el esquema acepta un foco de tarea opcional además del proyecto y los límites de presupuesto

#### Scenario: Vecinos de una semilla
- **WHEN** un cliente autenticado llama `related_memories` con el identificador de una memoria activa propia
- **THEN** recibe sólo vecinos temáticos de esa semilla (identificador, contenido, categoría, ámbito, proyecto y similitud), sin embeddings ni el grafo completo

#### Scenario: Semilla desconocida o ajena
- **WHEN** un cliente llama `related_memories` con un identificador desconocido, ajeno o retirado
- **THEN** recibe una lista vacía de vecinos sin revelar si el identificador existe para otro usuario

#### Scenario: Reconfirmación por identificador
- **WHEN** un cliente autenticado llama `reconfirm` con el identificador de una memoria activa propia
- **THEN** el sistema estampa la fecha de reconfirmación y devuelve la memoria actualizada con `reconfirmed=true`

#### Scenario: Reconfirmación de identificador desconocido o ajeno
- **WHEN** un cliente llama `reconfirm` con un identificador desconocido, ajeno o retirado
- **THEN** la respuesta indica `reconfirmed=false` sin revelar si pertenece a otro usuario

## ADDED Requirements

### Requirement: Prompts MCP del ciclo de memoria
El sistema MUST publicar exactamente los prompts `session-start`, `capture-scan` y `stale-review`. El sistema MUST NOT publicar ningún otro prompt. Ningún prompt MUST aceptar un selector de usuario.

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
- **THEN** la guía indica una captura final atómica en inglés vía `remember_batch`, sin secretos ni recapitulaciones

#### Scenario: stale-review
- **WHEN** un cliente obtiene el prompt `stale-review`
- **THEN** la guía indica enumerar la cola `list_memories(stale=true)` y resolver con `get_memory`, `reconfirm`, `update`, `forget` o `merge_memories`
