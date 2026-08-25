## MODIFIED Requirements

### Requirement: Conjunto mínimo de herramientas
El sistema MUST publicar las capacidades de guardado individual y por lotes, recuperación, contexto con foco opcional, lectura por identificador, enumeración, corrección, consolidación, vecinos temáticos, reconfirmación y borrado mediante las herramientas `remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm` y `forget`, y las capacidades de procedimiento mediante `save_skill`, `match_skills`, `get_skill` y `forget_skill`. El sistema MUST NOT publicar el grafo temático completo como herramienta MCP.

#### Scenario: Descubrimiento de herramientas
- **WHEN** un cliente autenticado solicita la lista de herramientas MCP
- **THEN** el sistema anuncia exactamente esas quince herramientas con esquemas de entrada y salida validados

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

#### Scenario: Skill propio
- **WHEN** un cliente autenticado llama `get_skill` con el identificador de un skill activo propio
- **THEN** recibe el skill completo

#### Scenario: Skill desconocido o ajeno
- **WHEN** un cliente llama `get_skill` o `forget_skill` con un identificador desconocido, ajeno o retirado
- **THEN** la respuesta indica no encontrado o no olvidado, sin revelar si pertenece a otro usuario
