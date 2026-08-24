## Purpose

Dar a los agentes de código un procedimiento versionado, recuperable y distinto de una memoria atómica: cuándo aplicar un método, no sólo qué ocurrió.

## ADDED Requirements

### Requirement: Skill como entidad distinta
El sistema MUST persistir skills atómicas de procedimiento, propiedad de un usuario, con ámbito `global` o `project` idéntico al de las memorias. Una skill MUST tener `name`, `description`, `triggers`, `steps` y `version` entero creciente. MUST NOT ser una memoria con `category` especial. El sistema MUST NOT ofrecer marketplace, compartir skills entre usuarios, ni un catálogo público.

#### Scenario: Guardar un skill de proyecto
- **WHEN** un usuario autenticado guarda un skill con nombre `create_database_migration` y un proyecto
- **THEN** el skill queda visible sólo en ese proyecto para ese usuario, más la visibilidad global habitual si se consulta con proyecto

#### Scenario: Aislamiento
- **WHEN** otro usuario busca skills
- **THEN** no recibe el skill ajeno

### Requirement: Matching de skills
El sistema MUST recuperar skills por consulta híbrida (señal vectorial y textual) sobre `description`, `triggers` y `steps`, degradando a textual si los embeddings no están disponibles, con el mismo aislamiento de usuario que las memorias.

#### Scenario: Disparo por descripción
- **WHEN** el usuario llama `match_skills` con una consulta sobre modificar el esquema de base de datos
- **THEN** puede devolver el skill `create_database_migration` si es suyo y está activo

#### Scenario: Degradación
- **WHEN** Ollama no está disponible
- **THEN** `match_skills` sigue devolviendo resultados textuales marcados como degradados

### Requirement: Ciclo de vida sin auto-extracción
El sistema MUST permitir guardar, leer, olvidar lógicamente y reemplazar un skill (nueva versión que retira la anterior, enlazada como las memorias sustituidas). MUST NOT extraer skills automáticamente de conversaciones o de sesiones. El guardado de un skill con el mismo nombre activo en el mismo ámbito MUST o bien devolver el existente (si el contenido de pasos es idéntico) o exigir un reemplazo explícito.

#### Scenario: Dedup por nombre y pasos
- **WHEN** se vuelve a guardar el mismo nombre y los mismos pasos en el mismo ámbito
- **THEN** no se crea una segunda fila activa

#### Scenario: Sin worker de extracción
- **WHEN** termina una sesión de agente
- **THEN** el servidor no crea skills por su cuenta
