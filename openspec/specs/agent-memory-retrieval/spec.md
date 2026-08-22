# Agent Memory Retrieval

## Purpose

Definir la recuperación híbrida, filtrada y compacta de memorias privadas para agentes.
## Requirements
### Requirement: Búsqueda híbrida de memorias
El sistema MUST recuperar memorias mediante señales vectoriales y textuales, aplicando aislamiento de usuario antes de ordenar los resultados.

#### Scenario: Recuperar por significado
- **WHEN** un usuario llama `recall` con una consulta semánticamente relacionada pero con palabras diferentes
- **THEN** el sistema puede devolver sus memorias vectorialmente relevantes dentro del límite solicitado

#### Scenario: Recuperar término exacto
- **WHEN** una consulta contiene un término técnico exacto presente en una memoria
- **THEN** la señal textual participa en el orden de relevancia del resultado

#### Scenario: Consulta sin resultados
- **WHEN** ninguna memoria activa del usuario satisface la consulta y los filtros
- **THEN** el sistema devuelve una lista vacía sin incluir memorias de otros usuarios

### Requirement: Filtros de recuperación
El sistema MUST permitir filtrar recuperación por ámbito global, proyecto y categoría sin aceptar un identificador de usuario proporcionado por el cliente.

#### Scenario: Recuperar contexto de proyecto
- **WHEN** un usuario consulta un proyecto concreto
- **THEN** el sistema considera sus memorias globales y las memorias de ese proyecto, excluyendo las de proyectos distintos

#### Scenario: Recuperar sólo decisiones
- **WHEN** un usuario filtra `recall` por la categoría `decision`
- **THEN** el sistema devuelve únicamente decisiones activas del ámbito solicitado

### Requirement: Contexto compacto de sesión
El sistema MUST generar contexto compacto con memorias globales y del proyecto respetando límites de
cantidad y caracteres, MUST aceptar un foco de tarea opcional que incorpore memorias relevantes a
ese foco antepuestas dentro de su propia categoría sin alterar el orden de categorías ni el
presupuesto del snapshot categorizado, MUST anteponer un bloque de perfil materializado bajo un
sub-presupuesto reservado que el foco y la selección por importancia MUST NOT desalojar, MUST
excluir del snapshot categorizado los identificadores ya presentes en el perfil para no duplicar
ítems, y MUST informar cuántas memorias activas visibles quedaron fuera del presupuesto total.
La respuesta de contexto MUST incluir metadatos del perfil (disponibilidad, `built_at` e integridad
cuando el perfil está disponible).

#### Scenario: Iniciar sesión de proyecto
- **WHEN** un agente llama `context` con un proyecto válido
- **THEN** el sistema devuelve el bloque de perfil aplicable, y preferencias globales y memorias relevantes de ese proyecto en grupos por categoría dentro del presupuesto restante

#### Scenario: Perfil no desalojado por el foco
- **WHEN** un agente llama `context` con un foco de tarea y un presupuesto ajustado
- **THEN** los ítems del perfil caben según el sub-presupuesto reservado antes de aplicar el foco y la importancia al resto, y el foco no elimina ítems del perfil ya incluidos

#### Scenario: Sin duplicar perfil en grupos
- **WHEN** una memoria aparece en el perfil materializado de la respuesta
- **THEN** no vuelve a aparecer como ítem en los grupos por categoría de esa misma respuesta

#### Scenario: Respetar el presupuesto de contexto
- **WHEN** existen más memorias relevantes que las permitidas por los límites solicitados
- **THEN** el sistema trunca sin exceder el máximo de elementos ni caracteres totales, contando el perfil dentro de ese total

#### Scenario: Contexto con foco de tarea
- **WHEN** un agente llama `context` con un foco de tarea
- **THEN** el resultado incluye además memorias recuperadas por relevancia híbrida frente a ese foco, deduplicadas contra el perfil y contra la selección por importancia, y antepuestas dentro de su categoría en el snapshot categorizado para sobrevivir al presupuesto restante

#### Scenario: Foco con embeddings caídos
- **WHEN** se solicita contexto con foco y el servicio de embeddings no está disponible
- **THEN** la parte enfocada se degrada a relevancia textual y el perfil y el snapshot por importancia se devuelven igualmente cuando estén disponibles

#### Scenario: Transparencia del presupuesto
- **WHEN** el presupuesto deja memorias fuera del resultado
- **THEN** la respuesta informa el total disponible y cuántas quedaron omitidas, además del indicador de truncado

#### Scenario: Ítem largo truncado con marca
- **WHEN** un ítem no cabe completo en el presupuesto de caracteres restante pero queda espacio razonable
- **THEN** el sistema incluye el ítem recortado marcándolo como truncado, en lugar de omitirlo y rellenar con ítems menos importantes

#### Scenario: Perfil no disponible
- **WHEN** el perfil materializado no puede obtenerse ni reconstruirse
- **THEN** `context` devuelve el snapshot categorizado como hasta ahora e indica perfil no disponible sin fallar la llamada

### Requirement: Omisiones de contexto accionables
El sistema MUST informar, cuando el presupuesto deja memorias fuera del resultado de `context`, un desglose por categoría de cuántas memorias activas visibles de esa categoría quedaron omitidas (sólo aparecen las categorías con al menos una omisión), MUST NOT incluir en ese desglose el contenido de las memorias omitidas, y el bloque de perfil MUST NOT contar como omitido en ninguna categoría.

#### Scenario: Desglose por categoría al truncar
- **WHEN** el presupuesto de `context` deja memorias de una o más categorías fuera del resultado
- **THEN** la respuesta incluye, por cada categoría con omisiones, cuántas memorias activas visibles de esa categoría no llegaron al resultado, sin listar su contenido

#### Scenario: Sin omisiones
- **WHEN** todas las memorias activas visibles caben dentro del presupuesto de `context`
- **THEN** el desglose por categoría de omisiones está ausente o vacío

#### Scenario: El perfil no cuenta como omitido
- **WHEN** una memoria queda incluida en el bloque de perfil materializado en lugar de en los grupos por categoría
- **THEN** esa memoria no incrementa el conteo de omitidas de su categoría

### Requirement: Snapshot único de context
Al armar `context`, el sistema MUST observar un único snapshot de base de datos para el perfil servido (static materializado más dynamic en lectura), los pools de importancia global y de proyecto, los candidatos de foco cuando hay `focus`, y el total de memorias activas visibles usado para `omitted`. Ese snapshot MUST respetar el aislamiento RLS del propietario. El registro de uso de las memorias servidas MUST ocurrir fuera de esa lectura y MUST NOT hacerla fallar.

#### Scenario: Un snapshot para perfil y grupos
- **WHEN** un agente llama `context` con un proyecto
- **THEN** el bloque de perfil, los grupos por categoría y el total informado corresponden al mismo conjunto visible de memorias activas en ese instante

#### Scenario: Foco en el mismo snapshot
- **WHEN** un agente llama `context` con `focus`
- **THEN** las memorias de foco se eligen sobre el mismo snapshot que el perfil y los pools de importancia, o se degradan a textual si los embeddings no están disponibles, sin fallar el resto

#### Scenario: Uso fuera de la lectura
- **WHEN** `context` devuelve ítems de perfil o de grupos
- **THEN** el intento de registrar esa exposición ocurre después de materializar el resultado y un fallo de registro no cambia ni retrasa el resultado ya decidido

### Requirement: Recall no invalida el perfil de context
Registrar uso de un `recall` MUST NOT obligar al siguiente `context` a reconstruir el perfil materializado. El siguiente `context` MUST poder reflejar esas recuperaciones recientes en el slice dynamic sin tratar el static como desactualizado.

#### Scenario: Context tras recall reusa static
- **WHEN** un usuario ejecuta `recall` y acto seguido llama `context` sin mutar memorias
- **THEN** el static del perfil coincide con la materialización previa y el dynamic puede incluir memorias recién recuperadas según la ventana de uso

### Requirement: Uso al servir el perfil en contexto
Cuando un ítem del perfil materializado se incluye en una respuesta de `context`, el sistema MUST registrarlo como uso de la memoria fuente con las mismas reglas de no-fallo que el registro de uso del snapshot categorizado.

#### Scenario: Perfil cuenta como uso
- **WHEN** una memoria fuente aparece en el bloque de perfil de `context`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza, o el fallo de registro no impide devolver el contexto

### Requirement: Degradación textual
El sistema MUST mantener búsquedas textuales disponibles cuando PostgreSQL funciona pero Ollama no puede generar el embedding de una consulta.

#### Scenario: Ollama no disponible durante recall
- **WHEN** el servicio de embeddings falla al procesar una consulta
- **THEN** `recall` devuelve resultados textuales marcando el modo degradado en la respuesta

### Requirement: Registro de uso al servir memorias
El sistema MUST registrar por memoria cuántas veces y cuándo fue servida en resultados de `recall` o
`context`, MUST exponer esos campos en las respuestas, y el registro MUST NOT hacer fallar la
lectura que lo origina.

#### Scenario: Memoria servida en recall
- **WHEN** una memoria aparece en el resultado final de `recall`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza

#### Scenario: Memoria servida en contexto
- **WHEN** una memoria aparece en un snapshot de `context`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza

#### Scenario: Registro de uso falla
- **WHEN** el registro de uso no puede completarse
- **THEN** el resultado de la lectura se devuelve igualmente sin error

#### Scenario: Enumeración no cuenta como uso
- **WHEN** una memoria aparece únicamente en `list_memories`
- **THEN** su contador de uso no cambia
