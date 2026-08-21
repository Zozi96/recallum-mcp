## ADDED Requirements

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
