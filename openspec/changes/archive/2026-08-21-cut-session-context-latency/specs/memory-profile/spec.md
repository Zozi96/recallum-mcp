## ADDED Requirements

### Requirement: Generation sólo por mutación de corpus
El contador de generación del usuario MUST incrementarse cuando una mutación cambie el conjunto de memorias activas o la elegibilidad del slice static (guardado, reconfirmación, actualización, sustitución, fusión, borrado o reasignación de proyecto). Registrar que una memoria fue recuperada por `recall` (contador y `last_recalled_at`) MUST NOT incrementar esa generación ni marcar el perfil materializado como desactualizado.

#### Scenario: Recall no ensucia generation
- **WHEN** un usuario llama `recall` y se registra uso en las memorias servidas
- **THEN** la generación del usuario no cambia y la fila materializada del perfil permanece válida para el slice static

#### Scenario: Remember sí incrementa generation
- **WHEN** un usuario guarda una memoria nueva
- **THEN** la generación del usuario incrementa y las claves de perfil afectadas quedan pendientes de reconstrucción static

### Requirement: Dynamic ensamblado en lectura
Al leer el perfil o al armar `context`, el sistema MUST ensamblar el slice dynamic a partir de las memorias activas visibles cuyo `last_recalled_at` cae en la ventana configurada, excluyendo las ya presentes en static, con los mismos topes de cantidad y caracteres que el perfil materializado. Ese ensamblado MUST NOT exigir una reconstrucción por generación. El slice static MUST seguir sirviéndose de la fila materializada (reconstruida si falta o su generación no coincide).

#### Scenario: Dynamic fresco tras recall sin rebuild
- **WHEN** una memoria activa acaba de ser servida por `recall` y no está en static
- **THEN** la siguiente lectura de perfil o `context` la incluye en dynamic si cabe en la ventana y el presupuesto, sin reconstruir la fila materializada

#### Scenario: Static no se reconstruye por recall
- **WHEN** la única actividad desde la última materialización es uno o más `recall`
- **THEN** el slice static servido coincide con la fila materializada vigente y `built_at` de esa fila no se actualiza

#### Scenario: Hash servido cubre ambos slices
- **WHEN** el perfil se sirve con static materializado y dynamic ensamblado en lectura
- **THEN** el resumen de integridad de la respuesta cubre los ítems static y dynamic realmente devueltos, y `built_at` refleja la última materialización del static

## MODIFIED Requirements

### Requirement: Reconstrucción perezosa al leer
Si al leer el perfil o al armar `context` no existe fila materializada, o la generación almacenada de esa fila no coincide con la generación actual del usuario, el sistema MUST reconstruir el slice static materializado antes de servir la lectura cuando sea posible. Un `recall` que sólo actualiza uso MUST NOT por sí mismo hacer que esa fila se considere desactualizada. Si la reconstrucción perezosa falla, la lectura MUST degradarse sin error fatal de sesión.

#### Scenario: Primera lectura sin fila
- **WHEN** un usuario llama a `context` y aún no hay perfil materializado
- **THEN** el sistema construye el perfil y lo incluye en la respuesta si la construcción tiene éxito

#### Scenario: Degradación
- **WHEN** la reconstrucción perezosa falla
- **THEN** la operación de lectura responde sin perfil usable e indica que el perfil no está disponible, sin fallar el resto del snapshot de contexto cuando aplique

#### Scenario: Generation coincidente no reconstruye static
- **WHEN** existe fila materializada cuya generación coincide con la del usuario
- **THEN** el sistema no reconstruye el static y sirve esa fila más el dynamic ensamblado en lectura
