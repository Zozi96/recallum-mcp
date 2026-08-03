## ADDED Requirements

### Requirement: Perfil materializado derivado de memorias activas
El sistema MUST mantener un perfil materializado por usuario (clave global) y MUST permitir una clave por proyecto, construido exclusivamente a partir de memorias activas del propietario. El perfil MUST NOT inventar hechos ni parafrasear contenido con un modelo de lenguaje: cada ítem MUST ser el contenido de una memoria fuente (posiblemente truncado para caber en el presupuesto del perfil).

#### Scenario: Perfil global vacío
- **WHEN** un usuario autenticado aún no tiene memorias activas que cumplan las reglas de selección
- **THEN** el sistema expone un perfil global disponible con listas estáticas y dinámicas vacías y un `built_at` reciente

#### Scenario: Ítems literales
- **WHEN** una memoria elegible entra en el perfil
- **THEN** el texto del ítem es el contenido de esa memoria (o un prefijo truncado del mismo) y el ítem referencia su identificador de memoria fuente

#### Scenario: Sin memorias ajenas
- **WHEN** se materializa o se lee el perfil de un usuario
- **THEN** ninguna memoria de otro usuario participa como fuente

### Requirement: Selección estática y dinámica
El perfil MUST separar un slice **static** y uno **dynamic**. El slice static MUST priorizar preferencias y restricciones activas y MAY incluir otras memorias activas de alta importancia según el umbral configurado del servidor. El slice dynamic MUST incluir memorias activas con uso reciente (`last_recalled_at` dentro de la ventana temporal configurada) que no estén ya en static. La mera creación reciente MUST NOT bastar para entrar en dynamic. Ambos slices MUST respetar topes de cantidad y caracteres del servidor y MUST excluir memorias retiradas o sustituidas.

#### Scenario: Preferencia global en static
- **WHEN** el usuario tiene una preferencia global activa
- **THEN** esa memoria es candidata al slice static del perfil global

#### Scenario: Hecho de alta importancia en static
- **WHEN** una memoria activa tiene importancia mayor o igual al umbral static del servidor y no es preferencia ni restricción
- **THEN** puede aparecer en static si cabe en el presupuesto de ese slice

#### Scenario: Dynamic por uso reciente
- **WHEN** una memoria activa fue recuperada por `recall` recientemente y no está en static
- **THEN** es candidata al slice dynamic mientras esté dentro de la ventana configurada

#### Scenario: Creación reciente sin recall
- **WHEN** una memoria activa fue creada recientemente pero nunca ha sido recuperada por `recall`
- **THEN** no entra en dynamic sólo por su fecha de creación

#### Scenario: Memoria retirada
- **WHEN** una memoria fuente se retira o se sustituye
- **THEN** deja de ser elegible y el perfil reconstruido ya no la incluye

### Requirement: Visibilidad por clave de perfil
La clave global del perfil MUST considerar sólo memorias de ámbito global. La clave de un proyecto MUST considerar las memorias visibles de ese proyecto (globales más las del proyecto) al construir sus slices, sin incluir memorias de otros proyectos.

#### Scenario: Perfil de proyecto no filtra otro proyecto
- **WHEN** existen memorias activas en el proyecto A y en el proyecto B
- **THEN** el perfil materializado del proyecto A no incluye memorias cuyo ámbito de proyecto es B

#### Scenario: Globales en clave de proyecto
- **WHEN** se construye el perfil de un proyecto y el usuario tiene preferencias globales
- **THEN** esas preferencias pueden formar parte de la selección de esa clave según las reglas de static/dynamic y la visibilidad global-and-project

### Requirement: Reconstrucción tras mutaciones
Tras un guardado, reconfirmación, actualización, fusión o borrado exitoso de una memoria, el sistema MUST intentar reconstruir las claves de perfil afectadas por esa memoria. Un fallo de reconstrucción MUST NOT hacer fallar la mutación de memoria.

#### Scenario: Remember reconstruye
- **WHEN** un usuario guarda una nueva preferencia global
- **THEN** el perfil global se reconstruye e incluye la nueva memoria si cabe en static

#### Scenario: Forget elimina del perfil
- **WHEN** el usuario borra una memoria que estaba en el perfil
- **THEN** la siguiente versión materializada ya no la lista como fuente

#### Scenario: Fallo de rebuild no revierte el remember
- **WHEN** la reconstrucción del perfil falla después de un remember exitoso
- **THEN** la memoria permanece guardada y el error de perfil no se propaga como fallo de remember

### Requirement: Reconstrucción perezosa al leer
Si al leer el perfil o al armar `context` no existe fila materializada, o la fila está desactualizada respecto al conjunto de memorias visibles relevantes, el sistema MUST reconstruir el perfil antes de servir la lectura cuando sea posible. Si la reconstrucción perezosa falla, la lectura MUST degradarse sin error fatal de sesión.

#### Scenario: Primera lectura sin fila
- **WHEN** un usuario llama a `context` y aún no hay perfil materializado
- **THEN** el sistema construye el perfil y lo incluye en la respuesta si la construcción tiene éxito

#### Scenario: Degradación
- **WHEN** la reconstrucción perezosa falla
- **THEN** la operación de lectura responde sin perfil usable e indica que el perfil no está disponible, sin fallar el resto del snapshot de contexto cuando aplique

### Requirement: Procedencia del perfil
Cada perfil materializado MUST exponer `built_at`, un resumen de integridad del contenido (`content_hash` o equivalente) y la lista ordenada de identificadores de memorias fuente usadas en los slices.

#### Scenario: Hash estable
- **WHEN** dos reconstrucciones producen los mismos ítems en el mismo orden
- **THEN** el valor de integridad del contenido coincide

#### Scenario: built_at actualizado
- **WHEN** el perfil se reconstruye tras un cambio elegible
- **THEN** `built_at` refleja el momento de esa reconstrucción
