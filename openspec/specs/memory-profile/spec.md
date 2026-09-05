# memory-profile Specification

## Purpose
Definir el perfil materializado por usuario para servir contexto literal, acotado y trazable.

## Requirements
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

### Requirement: Reconstrucción perezosa al leer
Si al leer el perfil o al armar `context` no existe fila materializada, o la generación almacenada de esa fila no coincide con la generación actual del usuario, el sistema MUST reconstruir el slice static materializado antes de servir la lectura cuando sea posible. Un `recall` que sólo actualiza uso MUST NOT por sí mismo hacer que esa fila se considere desactualizada. Si la reconstrucción perezosa falla por indisponibilidad del servicio de embeddings o por ausencia legítima de datos, la lectura MUST degradarse sin error fatal de sesión. Si la lectura o reconstrucción falla por un error de infraestructura de base de datos, el sistema MUST NOT enmascararlo como ausencia legítima de perfil: registra el fallo y la superficie de transporte traduce el error a su forma segura.

#### Scenario: Primera lectura sin fila
- **WHEN** un usuario llama a `context` y aún no hay perfil materializado
- **THEN** el sistema construye el perfil y lo incluye en la respuesta si la construcción tiene éxito

#### Scenario: Degradación
- **WHEN** la reconstrucción perezosa falla por una causa que no es de infraestructura de base de datos
- **THEN** la operación de lectura responde sin perfil usable e indica que el perfil no está disponible, sin fallar el resto del snapshot de contexto cuando aplique

#### Scenario: Fallo de base de datos no se enmascara como ausencia de perfil
- **WHEN** la lectura o reconstrucción del perfil falla por un error de base de datos
- **THEN** el fallo se registra en el servidor y la superficie MCP devuelve su forma de error segura, no un perfil marcado como no disponible

#### Scenario: Generation coincidente no reconstruye static
- **WHEN** existe fila materializada cuya generación coincide con la del usuario
- **THEN** el sistema no reconstruye el static y sirve esa fila más el dynamic ensamblado en lectura

### Requirement: Procedencia del perfil
Cada perfil materializado MUST exponer `built_at`, un resumen de integridad del contenido (`content_hash` o equivalente) y la lista ordenada de identificadores de memorias fuente usadas en los slices.

#### Scenario: Hash estable
- **WHEN** dos reconstrucciones producen los mismos ítems en el mismo orden
- **THEN** el valor de integridad del contenido coincide

#### Scenario: built_at actualizado
- **WHEN** el perfil se reconstruye tras un cambio elegible
- **THEN** `built_at` refleja el momento de esa reconstrucción
