## ADDED Requirements

### Requirement: Lectura del perfil materializado propio
El sistema MUST permitir que el usuario de la sesión consulte su perfil materializado global y, con un parámetro de proyecto opcional, la clave de proyecto correspondiente. La identidad MUST derivarse sólo de la sesión. La respuesta MUST incluir slices static y dynamic, procedencia (`built_at`, integridad, identificadores fuente) y MUST NOT exponer perfiles de otros usuarios.

#### Scenario: Perfil global autenticado
- **WHEN** un usuario con sesión válida solicita su perfil sin proyecto
- **THEN** el sistema devuelve el perfil global materializado de ese usuario

#### Scenario: Perfil de proyecto
- **WHEN** un usuario con sesión válida solicita su perfil indicando un proyecto
- **THEN** el sistema devuelve el perfil materializado de esa clave de proyecto

#### Scenario: Sesión ausente
- **WHEN** la petición de perfil llega sin sesión válida
- **THEN** el sistema la rechaza sin devolver datos de perfil

#### Scenario: Aislamiento
- **WHEN** se lee el perfil
- **THEN** la lectura se ejecuta con el aislamiento de usuario de la base de datos y no incluye memorias ajenas como fuente
