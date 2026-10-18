## MODIFIED Requirements

### Requirement: Degradación textual
El sistema MUST mantener búsquedas textuales disponibles cuando PostgreSQL funciona pero el embedding de una consulta no puede obtenerse dentro de un presupuesto temporal acotado de lectura. Agotado ese presupuesto — por fallo, por lentitud del servicio de embeddings o durante una ventana breve posterior a un fallo reciente — la lectura MUST degradarse a textual marcando el modo degradado donde corresponda, sin esperar el timeout completo pensado para escrituras.

#### Scenario: Ollama no disponible durante recall
- **WHEN** el servicio de embeddings falla al procesar una consulta
- **THEN** `recall` devuelve resultados textuales marcando el modo degradado en la respuesta

#### Scenario: Ollama lento durante una lectura
- **WHEN** el servicio de embeddings no responde dentro del presupuesto temporal de lectura
- **THEN** la lectura devuelve resultados textuales en modo degradado dentro de ese presupuesto, sin esperar a que el servicio responda

#### Scenario: Ventana posterior a un fallo
- **WHEN** una lectura degradó por indisponibilidad de embeddings y llega otra lectura dentro de la ventana breve posterior
- **THEN** esa lectura puede degradarse sin reintentar el embedding, y vencida la ventana el sistema vuelve a intentar el embedding y puede volver a servir en modo híbrido

### Requirement: Registro de uso al servir memorias
El sistema MUST registrar por memoria cuántas veces y cuándo fue servida en `recall` o `context`, y MUST exponer esos campos en las respuestas. El registro MUST NOT hacer fallar ni añadir espera de base de datos a la lectura que lo origina: MUST acumularse y aplicarse agrupado dentro de una ventana acotada, y MUST ser visible para la próxima asamblea del slice dynamic de ese usuario. Lo pendiente MUST estar acotado, MUST aplicarse en un cierre ordenado y su pérdida MUST ser observable.

#### Scenario: Memoria servida en recall
- **WHEN** una memoria aparece en el resultado final de `recall`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza a más tardar al cumplirse la ventana acotada, sin que la respuesta de `recall` espere esa escritura

#### Scenario: Memoria servida en contexto
- **WHEN** una memoria aparece en un snapshot de `context`
- **THEN** su contador de uso incrementa y su fecha de último uso se actualiza a más tardar al cumplirse la ventana acotada, sin que la respuesta de `context` espere esa escritura

#### Scenario: Dynamic ve el uso recién servido
- **WHEN** una memoria activa acaba de ser servida por `recall` y acto seguido, dentro de la misma ventana, se lee el perfil o `context` sin foco del mismo usuario
- **THEN** esa lectura la considera de uso reciente para el slice dynamic como si el registro ya estuviera aplicado, sin reconstruir el perfil materializado

#### Scenario: Registro de uso falla
- **WHEN** el registro de uso no puede completarse
- **THEN** el resultado de la lectura se devuelve igualmente sin error

#### Scenario: Enumeración no cuenta como uso
- **WHEN** una memoria aparece únicamente en `list_memories`
- **THEN** su contador de uso no cambia

#### Scenario: Cierre ordenado aplica lo pendiente
- **WHEN** la aplicación se detiene de forma controlada con registro de uso pendiente
- **THEN** el sistema lo aplica antes de terminar

#### Scenario: Terminación abrupta pierde como máximo la ventana pendiente
- **WHEN** la aplicación termina abruptamente con registro de uso pendiente
- **THEN** como máximo se pierde el uso aún no aplicado de esa ventana, ninguna memoria se ve afectada y la pérdida queda observable en la superficie de métricas
