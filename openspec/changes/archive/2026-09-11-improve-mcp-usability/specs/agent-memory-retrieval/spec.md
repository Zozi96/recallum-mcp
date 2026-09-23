## MODIFIED Requirements

### Requirement: Contexto compacto de sesión
El sistema MUST generar contexto compacto con memorias globales y del proyecto respetando límites de
cantidad y caracteres, MUST aceptar un foco de tarea opcional que incorpore memorias relevantes a
ese foco antepuestas dentro de su propia categoría sin alterar el orden de categorías ni el
presupuesto del snapshot categorizado, y MUST anteponer un bloque de perfil materializado bajo un
sub-presupuesto reservado. Ese bloque MUST contener exclusivamente static cuando el foco normalizado
no sea vacío, y static más dynamic por uso reciente cuando no haya foco. El foco y la selección
por importancia MUST NOT desalojar ítems static ya admitidos dentro del presupuesto reservado.
El sistema MUST excluir del snapshot categorizado únicamente los identificadores realmente servidos
en el perfil para no duplicar ítems; vaciar dynamic por foco MUST NOT excluir sus antiguos candidatos
de la recuperación ordinaria. MUST informar cuántas memorias activas visibles quedaron fuera del
presupuesto total. La respuesta de contexto MUST incluir metadatos del perfil (disponibilidad,
`built_at` e integridad cuando el perfil está disponible).

#### Scenario: Iniciar sesión de proyecto
- **WHEN** un agente llama `context` con un proyecto válido
- **THEN** el sistema devuelve el bloque de perfil aplicable, y preferencias globales y memorias relevantes de ese proyecto en grupos por categoría dentro del presupuesto restante

#### Scenario: Perfil no desalojado por el foco
- **WHEN** un agente llama `context` con un foco de tarea y un presupuesto ajustado
- **THEN** los ítems static caben según el sub-presupuesto reservado antes de aplicar el foco y la importancia al resto, y el foco no elimina ítems static ya incluidos; dynamic está vacío

#### Scenario: Sin duplicar perfil en grupos
- **WHEN** una memoria aparece en el perfil materializado de la respuesta
- **THEN** no vuelve a aparecer como ítem en los grupos por categoría de esa misma respuesta

#### Scenario: Respetar el presupuesto de contexto
- **WHEN** existen más memorias relevantes que las permitidas por los límites solicitados
- **THEN** el sistema trunca sin exceder el máximo de elementos ni caracteres totales, contando el perfil dentro de ese total

#### Scenario: Contexto con foco de tarea
- **WHEN** un agente llama `context` con un foco de tarea
- **THEN** el resultado incluye además memorias recuperadas por relevancia híbrida frente a ese foco, deduplicadas contra el perfil servido y contra la selección por importancia, y antepuestas dentro de su categoría en el snapshot categorizado para sobrevivir al presupuesto restante

#### Scenario: Recencia ajena no desplaza un hecho pertinente
- **WHEN** existen una restricción que ocupa una plaza static, un hecho reciente sin coincidencia con el foco y un hecho que sí coincide, ambos de categoría fact, y `max_items=2` con espacio suficiente en caracteres
- **THEN** la respuesta enfocada sirve la restricción en static y el hecho pertinente en el grupo fact; el hecho reciente ajeno no consume una plaza reservada

#### Scenario: Candidato dynamic pertinente sigue recuperable
- **WHEN** un hecho usado recientemente coincide con el foco y cabe en el presupuesto restante
- **THEN** puede entrar por la recuperación ordinaria y no se descarta por haber sido candidato dynamic

#### Scenario: Presupuesto agotado por reglas
- **WHEN** el presupuesto efectivo sólo permite los ítems static admitidos
- **THEN** los grupos están vacíos, las omisiones son correctas y el sistema no supera el presupuesto para forzar un resultado de foco

#### Scenario: Foco con embeddings caídos
- **WHEN** se solicita contexto con foco y el servicio de embeddings no está disponible
- **THEN** la parte enfocada se degrada a relevancia textual y el perfil static y el snapshot por importancia se devuelven igualmente cuando estén disponibles, manteniendo dynamic vacío

#### Scenario: Transparencia del presupuesto
- **WHEN** el presupuesto deja memorias fuera del resultado
- **THEN** la respuesta informa el total disponible y cuántas quedaron omitidas, además del indicador de truncado; los ítems no servidos de dynamic no cuentan como entregados

#### Scenario: Ítem largo truncado con marca
- **WHEN** un ítem no cabe completo en el presupuesto de caracteres restante pero queda espacio razonable
- **THEN** el sistema incluye el ítem recortado marcándolo como truncado, en lugar de omitirlo y rellenar con ítems menos importantes

#### Scenario: Perfil no disponible
- **WHEN** el perfil materializado no puede obtenerse ni reconstruirse por una causa con degradación definida
- **THEN** `context` devuelve el snapshot categorizado e indica perfil no disponible sin fallar la llamada; un fallo de infraestructura de base de datos conserva su error seguro según el contrato de perfil

### Requirement: Recall no invalida el perfil de context
Registrar uso de un `recall` MUST NOT obligar al siguiente `context` a reconstruir el perfil materializado. El siguiente `context` sin foco MUST poder reflejar esas recuperaciones recientes en el slice dynamic sin tratar el static como desactualizado. Con foco no vacío MUST conservar el mismo static vigente y servir dynamic vacío.

#### Scenario: Context tras recall reusa static
- **WHEN** un usuario ejecuta `recall` y acto seguido llama `context` sin foco y sin mutar memorias
- **THEN** el static del perfil coincide con la materialización previa y el dynamic puede incluir memorias recién recuperadas según la ventana de uso

#### Scenario: Context enfocado tras recall reusa static
- **WHEN** un usuario ejecuta `recall` y acto seguido llama `context` con foco sin mutar memorias
- **THEN** se reutiliza static sin reconstrucción y dynamic está vacío; la memoria recién recuperada sigue sujeta a la selección ordinaria del snapshot
