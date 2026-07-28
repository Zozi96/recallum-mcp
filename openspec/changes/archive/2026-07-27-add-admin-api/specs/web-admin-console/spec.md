## ADDED Requirements

### Requirement: Acceso restringido a administradores
Las operaciones de administración MUST requerir una sesión web válida cuyo usuario sea administrador, y MUST rechazar a cualquier otro usuario autenticado.

#### Scenario: Administrador autenticado
- **WHEN** un administrador con sesión válida realiza una operación de administración
- **THEN** el sistema la atiende

#### Scenario: Usuario ordinario autenticado
- **WHEN** un usuario sin condición de administrador intenta una operación de administración
- **THEN** el sistema la rechaza

#### Scenario: Sin sesión
- **WHEN** una operación de administración llega sin sesión válida
- **THEN** el sistema la rechaza sin revelar si el recurso existe

### Requirement: Enumeración de usuarios
El sistema MUST permitir a un administrador enumerar los usuarios existentes con su correo, fecha de alta, condición de administrador, si tienen acceso web y el número de credenciales activas. La respuesta MUST NOT incluir contraseñas ni secretos de credenciales.

#### Scenario: Listado de usuarios
- **WHEN** un administrador consulta los usuarios
- **THEN** el sistema devuelve la lista con el estado de acceso de cada uno

#### Scenario: Ausencia de secretos
- **WHEN** se inspecciona la respuesta
- **THEN** no contiene contraseñas, hashes ni secretos de API keys

### Requirement: Creación de usuarios
El sistema MUST permitir a un administrador crear un usuario indicando su correo, MUST rechazar correos ya registrados y MUST crear el usuario sin acceso web y sin condición de administrador salvo indicación explícita.

#### Scenario: Correo disponible
- **WHEN** un administrador crea un usuario con un correo no registrado
- **THEN** el sistema lo crea sin credenciales y sin acceso web

#### Scenario: Correo ya registrado
- **WHEN** el correo ya pertenece a un usuario
- **THEN** el sistema rechaza la creación y no modifica al usuario existente

#### Scenario: Estado inicial
- **WHEN** se consulta un usuario recién creado
- **THEN** no es administrador y no puede iniciar sesión en la web

### Requirement: Gestión de credenciales de cualquier usuario
El sistema MUST permitir a un administrador enumerar, emitir y revocar las API keys de cualquier usuario. La emisión MUST exigir la contraseña del administrador y devolver el secreto una única vez. La revocación MUST NOT exigirla.

#### Scenario: Enumerar credenciales ajenas
- **WHEN** un administrador consulta las keys de un usuario
- **THEN** el sistema devuelve su etiqueta, estado, fecha de creación y último uso, sin secretos

#### Scenario: Emitir con contraseña correcta
- **WHEN** un administrador emite una key para otro usuario aportando su propia contraseña
- **THEN** el sistema la crea y devuelve el secreto una sola vez

#### Scenario: Emitir sin contraseña válida
- **WHEN** falta la contraseña del administrador o es incorrecta
- **THEN** el sistema no crea ninguna key

#### Scenario: Revocar
- **WHEN** un administrador revoca una key de cualquier usuario
- **THEN** deja de autenticar llamadas de herramientas MCP y no se le pide la contraseña

### Requirement: Concesión y retirada de la condición de administrador
El sistema MUST permitir conceder y retirar la condición de administrador, y MUST rechazar toda retirada que dejaría al sistema sin ningún administrador.

#### Scenario: Conceder
- **WHEN** un administrador concede la condición a otro usuario
- **THEN** ese usuario pasa a poder realizar operaciones de administración

#### Scenario: Retirar con otros administradores presentes
- **WHEN** se retira la condición y queda al menos otro administrador
- **THEN** el sistema aplica el cambio

#### Scenario: Retirar al último administrador
- **WHEN** la retirada dejaría al sistema sin ningún administrador
- **THEN** el sistema la rechaza y no aplica el cambio

### Requirement: Imposibilidad de acceder a memorias ajenas
Las operaciones de administración MUST NOT devolver contenido de memorias de otros usuarios, y esa imposibilidad MUST estar garantizada por la base de datos y no por la capa de aplicación.

#### Scenario: Intento de lectura
- **WHEN** un administrador intenta obtener, buscar o enumerar memorias de otro usuario
- **THEN** el sistema no devuelve ninguna

#### Scenario: Garantía independiente de la aplicación
- **WHEN** se consultan memorias desde el contexto de administración
- **THEN** la base de datos no selecciona ninguna fila, con independencia de la lógica de aplicación

#### Scenario: Contenido ausente de los agregados
- **WHEN** se consultan los agregados del sistema
- **THEN** contienen recuentos y volúmenes pero ningún texto de memorias

### Requirement: Vista agregada del sistema
El sistema MUST ofrecer a un administrador el número de usuarios, el reparto de credenciales activas y revocadas, y el volumen de memorias por usuario, obteniendo estas últimas dentro del contexto de cada usuario.

#### Scenario: Sistema con datos
- **WHEN** un administrador consulta los agregados
- **THEN** el sistema devuelve los recuentos de usuarios, credenciales y memorias por usuario

#### Scenario: Usuario sin memorias
- **WHEN** un usuario no tiene ninguna memoria
- **THEN** aparece en los agregados con volumen cero

#### Scenario: Obtención de los recuentos
- **WHEN** se calculan los recuentos de memorias
- **THEN** se obtienen con el contexto de usuario activo, sin abrir ninguna sesión capaz de leer contenido ajeno

### Requirement: Estado operativo detallado
El sistema MUST ofrecer a un administrador el estado de las dependencias con más detalle que las sondas públicas, incluyendo la discordancia entre el modelo de embeddings configurado y el que produjo los vectores almacenados. La respuesta MUST NOT incluir credenciales ni cadenas de conexión.

#### Scenario: Dependencia caída
- **WHEN** la base de datos o el servicio de embeddings no responden
- **THEN** el estado indica cuál falla

#### Scenario: Modelo de embeddings discordante
- **WHEN** existen memorias cuyo vector procede de un modelo distinto del configurado
- **THEN** el estado lo señala

#### Scenario: Ausencia de secretos
- **WHEN** se inspecciona la respuesta de estado
- **THEN** no contiene credenciales, contraseñas ni cadenas de conexión

### Requirement: Borrado de usuarios excluido de la web
El sistema MUST NOT ofrecer el borrado de usuarios ni de sus memorias a través de la API web.

#### Scenario: Intento de borrado
- **WHEN** se intenta borrar un usuario desde la API web
- **THEN** la operación no existe

#### Scenario: Retirada de acceso
- **WHEN** un administrador necesita retirar el acceso de un usuario
- **THEN** puede hacerlo revocando sus credenciales, sin destruir sus memorias
