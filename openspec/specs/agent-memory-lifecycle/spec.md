# Agent Memory Lifecycle

## Purpose

Definir el ciclo de vida privado de memorias atómicas, desde su guardado y enumeración hasta su borrado explícito.
## Requirements
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
El sistema MUST evitar memorias activas duplicadas para el mismo usuario, ámbito y contenido
normalizado, y MUST registrar la fecha de reconfirmación cuando un contenido idéntico vuelve a
guardarse, exponiéndola en las respuestas como señal de frescura.

#### Scenario: Recordar el mismo hecho dos veces
- **WHEN** un usuario guarda nuevamente una memoria activa con el mismo contenido normalizado y ámbito
- **THEN** el sistema devuelve la memoria existente y no crea una segunda fila

#### Scenario: Reconfirmación con huella temporal
- **WHEN** un contenido idéntico a una memoria activa vuelve a guardarse
- **THEN** la memoria existente registra la fecha de reconfirmación y las respuestas posteriores la incluyen

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

### Requirement: Aviso de similares sin distinción de categoría
Al crear una memoria, el sistema MUST reportar las memorias activas preexistentes del mismo ámbito y
proyecto que traten el mismo asunto aunque estén archivadas bajo otra categoría, identificando la
categoría de cada similar; el aviso MUST ser únicamente informativo y su fallo MUST NOT impedir la
escritura.

#### Scenario: Similar en otra categoría
- **WHEN** se guarda como `fact` un contenido muy similar a una `decision` activa del mismo ámbito
- **THEN** la respuesta reporta esa memoria como similar indicando su categoría

#### Scenario: Fallo del aviso
- **WHEN** la detección de similares falla tras persistir la memoria
- **THEN** la memoria queda guardada y la respuesta omite el aviso sin error

### Requirement: Captura por lotes
El sistema MUST permitir guardar varias memorias atómicas en una sola operación acotada, aplicando a
cada ítem las mismas validaciones, deduplicación y aviso de similares que al guardado individual, y
MUST devolver el resultado de cada ítem de forma independiente con éxito parcial.

#### Scenario: Lote válido
- **WHEN** un agente envía un lote dentro del límite con ítems válidos
- **THEN** cada ítem se persiste con su propio resultado, incluyendo deduplicación y similares por ítem

#### Scenario: Lote con un ítem inválido
- **WHEN** un ítem del lote es inválido o su embedding falla
- **THEN** ese ítem devuelve su error y los demás ítems se procesan igualmente

#### Scenario: Lote fuera de límite
- **WHEN** el lote excede el máximo de ítems permitido o llega vacío
- **THEN** el sistema rechaza la operación completa sin persistir nada

### Requirement: Aviso de idioma no inglés
Al guardar una memoria, el sistema MUST advertir cuando el contenido parece no estar en inglés,
dado que el índice de texto completo y la deduplicación operan sobre el idioma inglés; el aviso
MUST ser únicamente informativo, MUST NOT bloquear ni fallar la escritura, y MUST aplicarse tanto a
memorias creadas como a las deduplicadas. El sistema MUST NOT marcar contenido compuesto
únicamente por identificadores, rutas, comandos o fragmentos de código, ni contenido demasiado
breve para juzgar el idioma.

#### Scenario: Contenido en español
- **WHEN** un usuario llama `remember` con una oración en español de varias palabras
- **THEN** la respuesta incluye un aviso de idioma sin impedir que la memoria se guarde

#### Scenario: Contenido en inglés
- **WHEN** un usuario llama `remember` con una oración en inglés
- **THEN** la respuesta no incluye aviso de idioma

#### Scenario: Identificadores y contenido breve
- **WHEN** el contenido guardado consiste sólo en identificadores, rutas o comandos, o es demasiado
  breve para evaluarse
- **THEN** la respuesta no incluye aviso de idioma aunque contenga palabras no inglesas aisladas

### Requirement: Reconfirmación explícita por identificador
El sistema MUST permitir estampar la fecha de reconfirmación de una memoria activa propia a partir de su identificador, sin reescribir el contenido. Identificadores desconocidos, ajenos o retirados MUST reportarse como no reconfirmados, de forma indistinguible.

#### Scenario: Reconfirmar una memoria propia
- **WHEN** el propietario reconfirma una memoria activa por identificador
- **THEN** la memoria conserva el mismo identificador y contenido, y las lecturas posteriores incluyen la nueva fecha de reconfirmación

#### Scenario: Reconfirmar un identificador inexistente o ajeno
- **WHEN** un usuario reconfirma un identificador que no corresponde a una memoria activa propia
- **THEN** el sistema responde como no reconfirmado sin revelar si pertenece a otro usuario


### Requirement: Reconciliación guiada ante similares
Cuando `remember` o `remember_batch` reportan similares, la guía del sistema (skill, prompts o documentación de agente) MUST distinguir: reexpresiones o refinamientos del mismo claim → `merge_memories`; hecho incorrecto u obsoleto → `update` del incorrecto; contradicción entre claims vigentes → `update` o `forget` del incorrecto tras verificación humana/agente, NEVER un merge que “resuelva” la contradicción. El servidor MUST NOT auto-merge ni auto-olvidar por el aviso de similares.

#### Scenario: Reexpresión del mismo claim
- **WHEN** los similares restatan el mismo claim subyacente con distinta redacción
- **THEN** la guía vigente indica consolidar con `merge_memories` y no crear otra copia vía `remember`

#### Scenario: Contradicción
- **WHEN** un similar afirma lo opuesto o incompatible
- **THEN** la guía vigente indica verificar y corregir con `update` o `forget`, y prohíbe usar `merge_memories` para resolver la contradicción

#### Scenario: Servidor no decide
- **WHEN** existen similares al guardar
- **THEN** la memoria nueva (o deduplicada) se persiste según las reglas actuales y el aviso permanece informativo sin mutar las similares

### Requirement: Desenlace explícito de la cola stale
La guía de higiene MUST exigir que cada memoria stale revisada termine en un desenlace explícito: `reconfirm` si sigue siendo cierta, `update` si cambió, `forget` si ya no aplica, o `merge_memories` si es reexpresión de otra activa. MUST NOT dejar la revisión en “ya la vi” sin una de esas acciones cuando la verificación concluyó.

#### Scenario: Stale aún cierta
- **WHEN** el agente verifica una memoria stale que sigue siendo verdadera
- **THEN** la guía exige `reconfirm` y no un `remember` idéntico

#### Scenario: Stale falsa
- **WHEN** el agente verifica una memoria stale que ya no es cierta
- **THEN** la guía exige `update` o `forget` según corresponda

#### Scenario: Stale duplicada
- **WHEN** varias stale o activas restatan el mismo claim
- **THEN** la guía exige `merge_memories` hacia una sola formulación en inglés
