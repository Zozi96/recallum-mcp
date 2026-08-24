## ADDED Requirements

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
