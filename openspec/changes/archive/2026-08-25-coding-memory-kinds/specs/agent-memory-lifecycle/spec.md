## ADDED Requirements

### Requirement: Kind opcional orthogonal a categoría
Una memoria MUST poder llevar un `kind` opcional entre `failure`, `solution`, `architecture`, `convention`, `todo` y `command`. `kind` MUST NOT reemplazar `category` (`preference`, `decision`, `constraint`, `fact`). El sistema MUST NOT persistir niveles de pirámide RAW/FACT/CONTEXT/CORE como `kind` ni como `category`. Filas existentes MUST tener `kind` nulo (sin clasificar).

#### Scenario: Hecho de arquitectura
- **WHEN** un usuario guarda `category=fact` y `kind=architecture`
- **THEN** la memoria se persiste con ambas dimensiones y las lecturas las exponen

#### Scenario: Sin kind
- **WHEN** `remember` omite `kind`
- **THEN** la memoria se guarda con `kind` nulo y sigue siendo válida

#### Scenario: Kind desconocido
- **WHEN** `kind` no está en el enumerado permitido
- **THEN** el sistema rechaza la operación sin persistir

### Requirement: TODO es memoria de trabajo
Una memoria con `kind=todo` MUST declarar un TTL (`ttl_seconds`). El sistema MUST rechazar un `todo` durable. Al expirar, el TODO deja de servirse como cualquier otra memoria expirada.

#### Scenario: Todo con TTL
- **WHEN** se guarda `kind=todo` con `ttl_seconds` válido
- **THEN** la memoria se persiste con expiración

#### Scenario: Todo durable rechazado
- **WHEN** se guarda `kind=todo` sin `ttl_seconds`
- **THEN** el sistema rechaza la operación
