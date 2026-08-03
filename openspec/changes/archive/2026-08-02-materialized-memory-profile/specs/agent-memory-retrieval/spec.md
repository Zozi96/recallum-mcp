## MODIFIED Requirements

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
- **WHEN** un ítem del snapshot categorizado no cabe completo en el presupuesto de caracteres restante pero queda espacio razonable
- **THEN** el sistema incluye el ítem recortado marcándolo como truncado, en lugar de omitirlo y rellenar con ítems menos importantes

#### Scenario: Perfil no disponible
- **WHEN** el perfil materializado no puede obtenerse ni reconstruirse
- **THEN** `context` devuelve el snapshot categorizado como hasta ahora e indica perfil no disponible sin fallar la llamada

## ADDED Requirements

### Requirement: Uso al servir el perfil en contexto
Cuando un ítem del perfil materializado se incluye en una respuesta de `context`, el sistema MUST registrarlo como uso de la memoria fuente con las mismas reglas de no-fallo que el registro de uso del snapshot categorizado.

#### Scenario: Perfil cuenta como uso
- **WHEN** una memoria fuente aparece en el bloque de perfil de `context`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza, o el fallo de registro no impide devolver el contexto
