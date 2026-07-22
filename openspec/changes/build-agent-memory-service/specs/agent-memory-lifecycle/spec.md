## ADDED Requirements

### Requirement: Guardado de memorias atómicas
El sistema MUST permitir que un usuario autenticado guarde una memoria atómica con contenido, categoría, ámbito, proyecto opcional, importancia y metadata limitada.

#### Scenario: Guardar una preferencia global
- **WHEN** un usuario autenticado llama `remember` con una preferencia válida y ámbito global
- **THEN** el sistema persiste la memoria asociada exclusivamente a ese usuario y devuelve su identificador

#### Scenario: Guardar una decisión de proyecto
- **WHEN** un usuario autenticado llama `remember` con una decisión y un proyecto válido
- **THEN** el sistema persiste la memoria en el ámbito de ese proyecto sin hacerla visible en otros proyectos salvo consulta explícita global

#### Scenario: Rechazar memoria inválida
- **WHEN** `remember` recibe contenido vacío, una categoría desconocida o metadata mayor al límite permitido
- **THEN** el sistema rechaza la operación sin persistir una memoria

### Requirement: Deduplicación exacta
El sistema MUST evitar memorias activas duplicadas para el mismo usuario, ámbito y contenido normalizado.

#### Scenario: Recordar el mismo hecho dos veces
- **WHEN** un usuario guarda nuevamente una memoria activa con el mismo contenido normalizado y ámbito
- **THEN** el sistema devuelve la memoria existente y no crea una segunda fila

### Requirement: Enumeración privada
El sistema MUST permitir enumerar únicamente las memorias activas del usuario autenticado mediante filtros y límites acotados.

#### Scenario: Enumerar memorias de un proyecto
- **WHEN** un usuario llama `list_memories` filtrando por proyecto y categoría
- **THEN** el sistema devuelve sólo sus memorias activas que cumplen ambos filtros

#### Scenario: Intentar enumerar memorias ajenas
- **WHEN** un usuario autenticado realiza cualquier enumeración
- **THEN** el sistema no devuelve memorias pertenecientes a otro usuario

### Requirement: Borrado explícito
El sistema MUST permitir que un usuario borre lógicamente una memoria propia mediante su identificador y MUST impedir borrar memorias ajenas.

#### Scenario: Borrar una memoria propia
- **WHEN** el propietario llama `forget` con el identificador de una memoria activa
- **THEN** el sistema marca la memoria como eliminada y deja de devolverla en cualquier consulta posterior

#### Scenario: Borrar una memoria inexistente o ajena
- **WHEN** un usuario llama `forget` con un identificador que no corresponde a una memoria activa propia
- **THEN** el sistema responde como no encontrada sin revelar si pertenece a otro usuario

### Requirement: Ausencia de conversaciones persistidas
El sistema MUST almacenar únicamente el contenido atómico enviado a `remember` y MUST NOT persistir transcripts completos ni prompts de sesión.

#### Scenario: Guardar memoria desde una conversación
- **WHEN** un agente extrae una decisión de una conversación y llama `remember`
- **THEN** el sistema conserva sólo la decisión enviada y metadata breve de procedencia
