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

### Requirement: Densidad útil de resultados recuperados
El sistema MUST tratar `limit` y `max_tokens` como límites máximos y MUST incluir en el resultado final de `recall` y en los candidatos recuperados por `context(focus=...)` únicamente memorias que alcancen evidencia mínima calibrada de utilidad para la consulta. El sistema MUST poder devolver menos ítems que el límite solicitado, MUST conservar memorias de soporte o contexto que aporten valor aunque no sean la respuesta esencial, y MUST mantener el aislamiento, los filtros y los presupuestos existentes. La configuración por defecto MUST estar respaldada por el evaluador versionado y MUST NOT depender de un reranker o contador de tokens remoto.

#### Scenario: El límite no se rellena con ruido
- **WHEN** sólo dos memorias alcanzan evidencia suficiente de utilidad y el usuario llama `recall` con `limit=10`
- **THEN** el sistema devuelve esas dos memorias sin completar el resultado con vecinos débiles

#### Scenario: Sin memoria útil
- **WHEN** ninguna memoria activa y visible alcanza evidencia suficiente para la consulta
- **THEN** `recall` devuelve una lista vacía aunque existan memorias que sean únicamente los vecinos disponibles más cercanos

#### Scenario: Contexto de soporte conservado
- **WHEN** una memoria responde directamente a la consulta y otra memoria aporta una restricción, consecuencia o procedimiento relevante dentro del presupuesto
- **THEN** ambas pueden aparecer en el resultado, ordenadas por la recuperación vigente, sin exigir que todo ítem sea una respuesta directa

#### Scenario: Foco de contexto usa la misma admisión
- **WHEN** `context` se llama con `focus` y algunos candidatos enfocados no alcanzan evidencia suficiente
- **THEN** esos candidatos no se incorporan a los grupos, mientras el perfil y la selección por importancia continúan bajo sus reglas existentes

#### Scenario: Degradación textual conserva utilidad
- **WHEN** los embeddings no están disponibles durante `recall` o `context(focus=...)`
- **THEN** el sistema aplica la admisión sobre las señales textuales disponibles, marca el modo degradado donde corresponda y no rellena el límite con memorias sin coincidencia textual válida

### Requirement: Evaluación reproducible de ranking
El proyecto MUST proporcionar un dataset versionado y un evaluador de ranking distinto del evaluador de flujo de checkpoints. El dataset MUST usar corpus e identificadores sintéticos o de fixture, MUST NOT requerir contenido de producción, MUST permitir comparar tunables de fusión y admisión de forma reproducible, y MUST admitir juicios graduados por consulta: `3` esencial, `2` soporte accionable, `1` contexto útil y `0` irrelevante. Cuando una consulta declara `relevance`, toda clave de corpus no declarada MUST seguir interpretándose como grado 0. El dataset MUST declarar un juicio explícito para cada clave que un `recall` baseline sirva dentro de `k` y para cada negativo difícil del mismo tema; MUST NOT dejar que la mayoría de los grado 0 servidos en el top-5 sean claves no declaradas. El evaluador MUST informar MRR y recall@k por compatibilidad, y MUST informar además `nDCG@5`, `essential-recall@3`, `irrelevant-rate@5`, la proporción estimada del presupuesto servido que corresponde a memorias con grado mayor que cero, `explicit-zero-rate@5` (sólo claves declaradas con grado 0) y `unjudged-rate@5` (claves servidas sin entrada en `relevance`), tanto globalmente como por etiqueta. `irrelevant-rate@5` MUST NOT cambiar de definición: undeclared sigue contando como 0. El dataset MUST incluir negativos difíciles y consultas multilingües capaces de detectar pérdida de contexto útil y colas irrelevantes.

#### Scenario: Informe de ranking
- **WHEN** el operador ejecuta el evaluador de ranking contra el dataset versionado
- **THEN** obtiene MRR, recall@k, las métricas graduadas, `explicit-zero-rate@5`, `unjudged-rate@5` y el detalle accionable de misses e irrelevantes sin mezclar métricas del flujo de checkpoints

#### Scenario: Comparar tunables
- **WHEN** se ejecuta el mismo dataset con dos configuraciones de fusión o admisión
- **THEN** el informe expone ambas y permite comparar las métricas heredadas y graduadas sin fabricar empates

#### Scenario: Informe de relevancia graduada
- **WHEN** el operador ejecuta el evaluador contra el dataset versionado
- **THEN** obtiene las métricas heredadas y las métricas graduadas, desglosadas por etiqueta, junto con las consultas que omitieron memorias esenciales o sirvieron memorias irrelevantes

#### Scenario: Comparar admisión y fusión
- **WHEN** se ejecuta el mismo dataset con el baseline y una configuración candidata
- **THEN** el informe permite comprobar si disminuye la tasa de irrelevantes sin reducir `essential-recall@3`, `nDCG@5` ni la densidad de contexto útil de las etiquetas protegidas

#### Scenario: Respuesta corta puntúa correctamente
- **WHEN** una configuración devuelve menos de `k` resultados, todos tienen juicio mayor que cero y no omite ninguna memoria juzgada útil
- **THEN** el evaluador no la penaliza por no rellenar `k` y refleja la ausencia de irrelevantes en las métricas correspondientes

#### Scenario: Negativo difícil detectado
- **WHEN** una consulta tiene una memoria esencial y otra memoria temáticamente cercana pero juzgada irrelevante
- **THEN** servir el negativo difícil reduce `nDCG@5`, aumenta `irrelevant-rate@5` y `explicit-zero-rate@5`, y aparece en el detalle accionable del informe

#### Scenario: Compatibilidad de dataset existente
- **WHEN** una consulta del dataset heredado sólo declara las claves esperadas sin juicios graduados
- **THEN** el evaluador sigue produciendo las métricas heredadas, marca sus métricas graduadas como no disponibles y no etiqueta automáticamente las demás memorias como irrelevantes

#### Scenario: Ceros explícitos separados de no juzgados
- **WHEN** el top-5 de una consulta juzgada contiene una clave declarada grado 0 y una clave ausente de `relevance`
- **THEN** ambas cuentan en `irrelevant-rate@5`, sólo la declarada cuenta en `explicit-zero-rate@5`, y sólo la ausente cuenta en `unjudged-rate@5`

#### Scenario: Dataset denso respecto al baseline
- **WHEN** se ejecuta el evaluador con admisión vectorial desactivada sobre el dataset versionado
- **THEN** cada clave servida en el top-k de cada consulta tiene un juicio explícito en `relevance` y `unjudged-rate@5` es 0.0

### Requirement: Voto de uso en la fusión de recall
La fusión de `recall` MUST poder incorporar un voto derivado del uso registrado (`recall_count` / señales de servicio ya persistidas) mediante un peso configurable. El valor por defecto MUST ser 0.0 (sin efecto). Un peso mayor que cero MUST NOT activarse como default de producción sin un experimento documentado que compare el baseline (peso 0) usando el evaluador de ranking. El voto de uso MUST NOT superar la fuerza de una señal de recuperación primaria, MUST respetar aislamiento por usuario, y MUST seguir aplicando en modo degradado sólo sobre candidatos textuales válidos.

#### Scenario: Default sin efecto
- **WHEN** `recall_usage_weight` está en 0.0
- **THEN** el orden de `recall` coincide con la fusión de relevancia/importancia vigente sin reordenar por uso

#### Scenario: Peso positivo medido
- **WHEN** un operador configura un peso de uso > 0 tras comparar el dataset de ranking
- **THEN** memorias con mayor uso pueden desempatar o reordenar candidatos ya cercanos en relevancia, sin desalojar un match claramente mejor

#### Scenario: Aislamiento intacto
- **WHEN** la fusión aplica el voto de uso
- **THEN** sólo participan memorias activas del usuario autenticado

### Requirement: Voto de frescura en la fusión de recall
La fusión de `recall` MAY incorporar un voto derivado de la última confirmación de una memoria (`reconfirmed_at`, o `created_at` cuando nunca fue reconfirmada) mediante un peso configurable. El valor por defecto MUST ser 0.0 (sin efecto). Un peso mayor que cero MUST NOT activarse como default de producción sin un experimento documentado que compare el baseline (peso 0) usando el evaluador de ranking. El voto de frescura MUST NOT superar la fuerza de una señal de recuperación primaria, y el modo degradado MUST seguir aplicando sólo sobre candidatos textuales válidos.

#### Scenario: Default sin efecto
- **WHEN** `recall_freshness_weight` está en 0.0
- **THEN** el orden de `recall` coincide con la fusión de relevancia/importancia/uso vigente sin reordenar por frescura

#### Scenario: Peso positivo medido
- **WHEN** un operador configura un peso de frescura > 0 tras comparar el dataset de ranking
- **THEN** memorias confirmadas más recientemente pueden desempatar o reordenar candidatos ya cercanos en relevancia, sin desalojar un match claramente mejor

#### Scenario: Frescura uniforme no aporta señal
- **WHEN** todas las memorias candidatas comparten el mismo instante de confirmación
- **THEN** el voto de frescura no altera el orden resultante de la fusión

### Requirement: Presupuesto de tokens además de ítems
El sistema MUST permitir que `recall` y `context` acepten un límite opcional de tokens estimados (`max_tokens`) además de los límites de ítems (y, en `context`, de caracteres) ya existentes. Cuando `max_tokens` está ausente, el empaquetado MUST coincidir con el comportamiento actual. Cuando está presente, el sistema MUST dejar de añadir memorias al resultado en cuanto la siguiente memoria completa excedería el presupuesto de tokens, sin omitir una memoria ya empezada a mitad de su contenido en `recall` (en `context` sigue aplicando el recorte marcado `content_truncated` sólo bajo las reglas de caracteres ya especificadas). La estimación de tokens MUST ser determinista, local y sin llamada a un modelo.

#### Scenario: Recall limitado por tokens
- **WHEN** un usuario llama `recall` con `max_tokens` menor que el tamaño combinado de los candidatos que cabrían en `limit`
- **THEN** el resultado contiene un prefijo del ranking que cabe en el presupuesto y no incluye la siguiente memoria que lo excedería

#### Scenario: Sin max_tokens
- **WHEN** `recall` o `context` se invocan sin `max_tokens`
- **THEN** el recorte sigue siendo únicamente por `limit` / `max_items` / `max_chars` como hasta ahora

#### Scenario: Estimación sin modelo
- **WHEN** se empaqueta un resultado
- **THEN** no se invoca Ollama ni ningún otro modelo para contar tokens

### Requirement: Estrategia de empaquetado por tipo de tarea
El sistema MUST aceptar un `strategy` opcional entre `coding`, `debugging`, `planning`, `review` y `architecture`. La estrategia MUST aplicarse sólo después de la recuperación híbrida existente: reordena los candidatos ya fusionados para llenar el presupuesto con las categorías (y, si existe, `kind`) prioritarias de esa estrategia, sin excluir un candidato de otra categoría si aún cabe presupuesto. Ausencia de `strategy` MUST conservar el orden actual (fusión RRF para `recall`; orden de categorías de `context`).

#### Scenario: Debugging prioriza hechos de fallo
- **WHEN** `recall` se llama con `strategy=debugging` y hay candidatos tanto `fact` como `preference`
- **THEN** los hechos relevantes al query se empaquetan antes que las preferencias, siempre que ambos hayan sido recuperados por la fusión

#### Scenario: Estrategia no filtra el corpus
- **WHEN** la única memoria que coincide con la consulta es una `preference` y `strategy=debugging`
- **THEN** esa preferencia puede aparecer en el resultado

#### Scenario: Estrategia desconocida
- **WHEN** `strategy` no es uno de los valores permitidos
- **THEN** el sistema rechaza la operación sin recuperar

### Requirement: Filtro opcional por kind
`recall`, `list_memories` y `context` MUST aceptar un filtro opcional `kind`. Cuando está presente, el sistema MUST restringir el conjunto candidato a memorias con ese `kind`. Las memorias con `kind` nulo MUST NO coincidir con un filtro concreto. Ausencia del filtro MUST incluir todos los kinds.

#### Scenario: Recall de fallos
- **WHEN** `recall` se llama con `kind=failure`
- **THEN** el resultado no incluye memorias de otro kind ni las de kind nulo

#### Scenario: Sin filtro
- **WHEN** `recall` se llama sin `kind`
- **THEN** participan memorias de cualquier kind, incluidas las nulas

### Requirement: Filtro por símbolo o archivo
`recall` MUST aceptar `symbol` y/o `file` opcionales. Cuando están presentes, el conjunto candidato MUST restringirse a memorias que tengan un ancla coincidente (igualdad normalizada: trim, NFC) **antes** de fusionar señales. El texto de la consulta MUST seguir pudiendo usarse sobre ese subconjunto. Ausencia de filtro MUST no exigir anclas.

#### Scenario: Recall por símbolo
- **WHEN** `recall` se llama con `symbol=PaymentService.capture`
- **THEN** el resultado sólo incluye memorias ancladas a ese símbolo (del usuario, activas)

#### Scenario: Símbolo sin memorias
- **WHEN** no hay anclas coincidentes
- **THEN** el resultado está vacío aunque existan memorias semánticamente similares sin ancla

#### Scenario: Consulta libre sigue funcionando
- **WHEN** `recall` se llama con query `PaymentService.capture` sin filtro `symbol`
- **THEN** las piernas FTS y trigram existentes pueden devolver memorias que mencionan el identificador en el contenido, tengan o no ancla
