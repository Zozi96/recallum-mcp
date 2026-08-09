## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Presupuesto constante de consultas administrativas
El sistema MUST ejecutar listados, agregados y comprobaciones globales de mismatch con un número de consultas que no crezca con el número de usuarios.

#### Scenario: Cardinalidad creciente
- **WHEN** la misma operación administrativa se ejecuta con diez y con miles de usuarios usando la misma página
- **THEN** el número de consultas permanece dentro del mismo presupuesto constante

#### Scenario: Mismatch de modelo global
- **WHEN** el administrador consulta status y existe al menos una memoria producida por otro modelo
- **THEN** el sistema detecta el mismatch con una consulta existencial global y no con una consulta por usuario

