# Agent Memory Retrieval (delta)

## MODIFIED Requirements

### Requirement: Contexto compacto de sesión
El sistema MUST generar contexto compacto con memorias globales y del proyecto respetando límites de
cantidad y caracteres, MUST aceptar un foco de tarea opcional que incorpore memorias relevantes a
ese foco antepuestas dentro de su propia categoría sin alterar el orden de categorías ni el
presupuesto, y MUST informar cuántas memorias activas visibles quedaron fuera del presupuesto.

#### Scenario: Iniciar sesión de proyecto
- **WHEN** un agente llama `context` con un proyecto válido
- **THEN** el sistema devuelve preferencias globales y memorias relevantes de ese proyecto ordenadas y agrupadas por categoría

#### Scenario: Respetar el presupuesto de contexto
- **WHEN** existen más memorias relevantes que las permitidas por los límites solicitados
- **THEN** el sistema trunca por relevancia sin exceder el máximo de elementos ni caracteres

#### Scenario: Contexto con foco de tarea
- **WHEN** un agente llama `context` con un foco de tarea
- **THEN** el resultado incluye además memorias recuperadas por relevancia híbrida frente a ese foco, deduplicadas contra la selección por importancia y antepuestas dentro de su categoría para sobrevivir al presupuesto

#### Scenario: Foco con embeddings caídos
- **WHEN** se solicita contexto con foco y el servicio de embeddings no está disponible
- **THEN** la parte enfocada se degrada a relevancia textual y el snapshot por importancia se devuelve igualmente

#### Scenario: Transparencia del presupuesto
- **WHEN** el presupuesto deja memorias fuera del resultado
- **THEN** la respuesta informa el total disponible y cuántas quedaron omitidas, además del indicador de truncado

#### Scenario: Ítem largo truncado con marca
- **WHEN** un ítem no cabe completo en el presupuesto de caracteres restante pero queda espacio razonable
- **THEN** el sistema incluye el ítem recortado marcándolo como truncado, en lugar de omitirlo y rellenar con ítems menos importantes

## ADDED Requirements

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
