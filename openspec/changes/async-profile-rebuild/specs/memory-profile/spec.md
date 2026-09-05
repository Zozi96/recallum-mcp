## MODIFIED Requirements

### Requirement: Reconstrucción tras mutaciones
Tras un guardado, reconfirmación, actualización, fusión o borrado exitoso de una memoria, el sistema MUST registrar las claves de perfil afectadas por esa memoria como pendientes de reconstrucción y MUST NOT ejecutar la reconstrucción en línea dentro de la petición de escritura. La materialización pendiente SHOULD reponerla un trabajador en segundo plano; en su ausencia, la reconstrucción perezosa al leer MUST reponerla. Un fallo de reconstrucción MUST NOT hacer fallar la mutación de memoria.

#### Scenario: Remember reconstruye
- **WHEN** un usuario guarda una nueva preferencia global y se completa la reconstrucción pendiente (trabajador o lectura perezosa)
- **THEN** el perfil global incluye la nueva memoria si cabe en static

#### Scenario: Forget elimina del perfil
- **WHEN** el usuario borra una memoria que estaba en el perfil y se completa la reconstrucción pendiente
- **THEN** ninguna versión materializada posterior la lista como fuente

#### Scenario: Fallo de rebuild no revierte el remember
- **WHEN** la reconstrucción del perfil falla después de un remember exitoso
- **THEN** la memoria permanece guardada y el error de perfil no se propaga como fallo de remember

#### Scenario: La escritura no espera la reconstrucción
- **WHEN** un usuario guarda una memoria en un corpus grande
- **THEN** la petición de escritura devuelve sin esperar a que la reconstrucción del perfil complete

#### Scenario: Lectura nunca sirve perfil anterior a la última mutación confirmada
- **WHEN** un `context` o una lectura de perfil llega antes de que el trabajador reponga la clave afectada
- **THEN** la lectura detecta la generación pendiente y reconstruye el slice static en el momento antes de responder

### Requirement: Generation sólo por mutación de corpus
El contador de generación del usuario MUST incrementarse cuando una mutación cambie el conjunto de memorias activas o la elegibilidad del slice static (guardado, reconfirmación, actualización, sustitución, fusión, borrado o reasignación de proyecto). Registrar que una memoria fue recuperada por `recall` (contador y `last_recalled_at`) MUST NOT incrementar esa generación ni marcar el perfil materializado como desactualizado. El incremento de generación es la señal que deja las claves pendientes; la reconstrucción propia puede ser diferida.

#### Scenario: Recall no ensucia generation
- **WHEN** un usuario llama `recall` y se registra uso en las memorias servidas
- **THEN** la generación del usuario no cambia y la fila materializada del perfil permanece válida para el slice static

#### Scenario: Remember sí incrementa generation
- **WHEN** un usuario guarda una memoria nueva
- **THEN** la generación del usuario incrementa y las claves de perfil afectadas quedan pendientes de reconstrucción static
