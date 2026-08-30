## MODIFIED Requirements

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
