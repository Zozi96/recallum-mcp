## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Evaluación reproducible de ranking
El proyecto MUST proporcionar un dataset versionado y un evaluador de ranking distinto del evaluador de flujo de checkpoints. El dataset MUST usar corpus e identificadores sintéticos o de fixture, MUST NOT requerir contenido de producción, MUST permitir comparar tunables de fusión y admisión de forma reproducible, y MUST admitir juicios graduados por consulta: `3` esencial, `2` soporte accionable, `1` contexto útil y `0` irrelevante. El evaluador MUST informar MRR y recall@k por compatibilidad, y MUST informar además `nDCG@5`, `essential-recall@3`, `irrelevant-rate@5` y la proporción estimada del presupuesto servido que corresponde a memorias con grado mayor que cero, tanto globalmente como por etiqueta. El dataset MUST incluir negativos difíciles y consultas multilingües capaces de detectar pérdida de contexto útil y colas irrelevantes.

#### Scenario: Informe de ranking
- **WHEN** el operador ejecuta el evaluador de ranking contra el dataset versionado
- **THEN** obtiene MRR, recall@k, las métricas graduadas y el detalle accionable de misses e irrelevantes sin mezclar métricas del flujo de checkpoints

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
- **THEN** servir el negativo difícil reduce `nDCG@5`, aumenta `irrelevant-rate@5` y aparece en el detalle accionable del informe

#### Scenario: Compatibilidad de dataset existente
- **WHEN** una consulta del dataset heredado sólo declara las claves esperadas sin juicios graduados
- **THEN** el evaluador sigue produciendo las métricas heredadas, marca sus métricas graduadas como no disponibles y no etiqueta automáticamente las demás memorias como irrelevantes
