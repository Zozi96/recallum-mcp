## MODIFIED Requirements

### Requirement: Selección estática y dinámica
El perfil MUST separar un slice **static** y uno **dynamic**. El slice static MUST admitir exclusivamente memorias activas de categoría `preference` o `constraint`; la importancia MUST ordenar candidatos elegibles, pero MUST NOT convertir hechos o decisiones en candidatos static. Las memorias excluidas de static MUST permanecer disponibles para recuperación ordinaria según su visibilidad. El slice dynamic MUST seleccionar memorias activas con uso reciente (`last_recalled_at` dentro de la ventana temporal configurada) que no estén ya en static, excepto en `context` con foco no vacío, donde MUST estar vacío. La mera creación reciente MUST NOT bastar para entrar en dynamic. Ambos slices MUST respetar topes de cantidad y caracteres del servidor y MUST excluir memorias retiradas o sustituidas.

#### Scenario: Preferencia global en static
- **WHEN** el usuario tiene una preferencia global activa
- **THEN** esa memoria es candidata al slice static del perfil global

#### Scenario: Restricción de baja importancia
- **WHEN** existe una restricción activa de baja importancia y espacio para ella en static
- **THEN** la restricción es elegible sin exigir el antiguo umbral de importancia

#### Scenario: Hecho de alta importancia en static
- **WHEN** una memoria activa es un hecho o una decisión de importancia máxima
- **THEN** no aparece en static y sigue recuperable mediante `recall` y los grupos de `context` cuando satisface sus criterios

#### Scenario: Dynamic por uso reciente
- **WHEN** una memoria activa fue recuperada por `recall` recientemente, no está en static y se lee el recurso de perfil o se solicita `context` sin foco
- **THEN** es candidata al slice dynamic mientras esté dentro de la ventana configurada

#### Scenario: Creación reciente sin recall
- **WHEN** una memoria activa fue creada recientemente pero nunca ha sido recuperada por `recall`
- **THEN** no entra en dynamic sólo por su fecha de creación

#### Scenario: Memoria retirada
- **WHEN** una memoria fuente se retira o se sustituye
- **THEN** deja de ser elegible y el perfil reconstruido ya no la incluye

### Requirement: Dynamic ensamblado en lectura
Al leer el recurso de perfil o al armar `context` sin foco no vacío, el sistema MUST ensamblar el slice dynamic a partir de las memorias activas visibles cuyo `last_recalled_at` cae en la ventana configurada, excluyendo las ya presentes en static, con los mismos topes de cantidad y caracteres que el perfil materializado. En `context` con foco no vacío el sistema MUST servir `dynamic=[]`, sin impedir que esas memorias participen en los grupos ordinarios por foco o importancia. Ese ensamblado MUST NOT exigir una reconstrucción por generación. El slice static MUST seguir sirviéndose de la fila materializada (reconstruida si falta o su generación no coincide).

#### Scenario: Dynamic fresco tras recall sin rebuild
- **WHEN** una memoria activa acaba de ser servida por `recall`, no está en static y la siguiente lectura es del recurso de perfil o de `context` sin foco
- **THEN** la lectura la incluye en dynamic si cabe en la ventana y el presupuesto, sin reconstruir la fila materializada

#### Scenario: Context enfocado no reserva recencia
- **WHEN** se solicita `context` con un foco que contiene texto distinto de espacios
- **THEN** el perfil servido contiene static y un dynamic vacío, aunque existan memorias con uso reciente

#### Scenario: Foco vacío conserva dynamic
- **WHEN** se omite `focus` o se envía una cadena vacía o compuesta sólo por espacios
- **THEN** dynamic se ensambla con la ventana de uso reciente habitual

#### Scenario: Static no se reconstruye por recall
- **WHEN** la única actividad desde la última materialización es uno o más `recall`
- **THEN** el slice static servido coincide con la fila materializada vigente y `built_at` de esa fila no se actualiza

#### Scenario: Hash servido cubre ambos slices
- **WHEN** el perfil se sirve con static materializado y dynamic ensamblado en lectura o vacío por foco
- **THEN** el resumen de integridad de la respuesta cubre los ítems static y dynamic realmente devueltos, y `built_at` refleja la última materialización del static

## ADDED Requirements

### Requirement: Actualización de política sin alterar memorias fuente
La actualización a la política de static restringido MUST invalidar los perfiles derivados de la política anterior antes de servirlos con la nueva versión. La siguiente lectura MUST reconstruirlos mediante el ciclo de reconstrucción existente. La actualización MUST NOT borrar, reclasificar, traducir ni modificar la importancia o los contadores de las memorias fuente y MUST conservar la visibilidad por usuario y proyecto.

#### Scenario: Perfil anterior con un hecho fijado
- **WHEN** se actualiza una instalación que ya tiene un perfil materializado con un hecho de alta importancia en static
- **THEN** la primera lectura con la nueva versión no sirve ese hecho en static, aunque no haya ocurrido una mutación posterior del corpus

#### Scenario: Corpus intacto
- **WHEN** termina la invalidación de perfiles derivados durante la actualización
- **THEN** las memorias fuente conservan identificadores, contenidos, categorías, importancia, ámbito y contadores, y siguen sujetas al aislamiento previo
