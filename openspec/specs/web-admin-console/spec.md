# Web Admin Console

## Purpose

Definir la administración web de usuarios, credenciales y estado agregado sin acceso al contenido de memorias ajenas.

## Requirements

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
El sistema MUST permitir a un administrador enumerar los usuarios existentes mediante páginas acotadas con su correo, fecha de alta, condición de administrador, si tienen acceso web y el número de credenciales activas. La respuesta MUST publicar el total sin materializar usuarios fuera de la página y MUST NOT incluir contraseñas ni secretos de credenciales.

#### Scenario: Listado de usuarios
- **WHEN** un administrador consulta una página con `limit` y `offset` válidos
- **THEN** el sistema devuelve sólo esa página con el estado de acceso de cada usuario y el total disponible

#### Scenario: Ausencia de secretos
- **WHEN** se inspecciona la respuesta
- **THEN** no contiene contraseñas, hashes ni secretos de API keys

#### Scenario: Página por defecto y máximo
- **WHEN** el administrador omite la página o solicita un límite mayor al máximo
- **THEN** el sistema aplica el default documentado o rechaza el límite fuera de rango sin ejecutar una consulta sin cota

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
El sistema MUST ofrecer a un administrador el número de usuarios, el reparto de credenciales activas y revocadas, y páginas acotadas del volumen de memorias por usuario, obteniendo los recuentos sin abrir acceso a contenido de memorias ajenas.

#### Scenario: Sistema con datos
- **WHEN** un administrador consulta los agregados y una página de volúmenes
- **THEN** el sistema devuelve los recuentos globales y sólo los volúmenes de usuario de la página solicitada

#### Scenario: Usuario sin memorias
- **WHEN** un usuario de la página no tiene ninguna memoria
- **THEN** aparece en los agregados con volumen cero

#### Scenario: Obtención de los recuentos
- **WHEN** se calculan los recuentos de memorias
- **THEN** se obtienen mediante agregación aislada por propietario sin abrir ninguna sesión capaz de leer contenido ajeno

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

### Requirement: Presupuesto constante de consultas administrativas
El sistema MUST ejecutar listados, agregados y comprobaciones globales de mismatch con un número de consultas que no crezca con el número de usuarios.

#### Scenario: Cardinalidad creciente
- **WHEN** la misma operación administrativa se ejecuta con diez y con miles de usuarios usando la misma página
- **THEN** el número de consultas permanece dentro del mismo presupuesto constante

#### Scenario: Mismatch de modelo global
- **WHEN** el administrador consulta status y existe al menos una memoria producida por otro modelo
- **THEN** el sistema detecta el mismatch con una consulta existencial global y no con una consulta por usuario
