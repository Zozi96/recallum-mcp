## ADDED Requirements

### Requirement: Autenticación de recursos MCP
Toda lectura o listado de recursos MCP MUST exigir la misma autenticación por API key Bearer que las herramientas y MUST derivar de ella la identidad del usuario. El sistema MUST NOT exponer recursos legibles sin credenciales válidas.

#### Scenario: Recurso con token válido
- **WHEN** un cliente autenticado lee un recurso de perfil publicado
- **THEN** el sistema devuelve el perfil del usuario asociado a la API key

#### Scenario: Recurso sin token
- **WHEN** un cliente sin token o con token inválido intenta listar o leer recursos
- **THEN** el sistema rechaza la operación sin devolver contenido de memorias ni del perfil

### Requirement: Recurso de perfil de memoria
El sistema MUST publicar un recurso MCP de sólo lectura para el perfil materializado del usuario autenticado, con variante global y con proyecto opcional, y MUST NOT añadir herramientas de escritura ni una herramienta dedicada de lectura de perfil mientras el recurso esté disponible.

#### Scenario: Descubrimiento del recurso
- **WHEN** un cliente autenticado lista los recursos MCP
- **THEN** aparece el recurso de perfil de Recallum

#### Scenario: Lectura de perfil global
- **WHEN** un cliente autenticado lee el recurso de perfil sin proyecto
- **THEN** recibe el perfil global materializado de su usuario (slices, procedencia y disponibilidad)

#### Scenario: Lectura de perfil de proyecto
- **WHEN** un cliente autenticado lee el recurso de perfil para un proyecto concreto
- **THEN** recibe el perfil materializado de esa clave de proyecto para su usuario

#### Scenario: Sin selectores de usuario en el recurso
- **WHEN** se inspecciona el URI o los parámetros del recurso de perfil
- **THEN** no existe un parámetro que permita seleccionar el perfil de otro usuario

### Requirement: Contexto MCP incluye perfil
La herramienta `context` MUST devolver el bloque de perfil materializado y sus metadatos según la capacidad de recuperación, sin cambiar el nombre de la herramienta ni añadir herramientas nuevas para obtener el perfil.

#### Scenario: Respuesta de context con perfil
- **WHEN** un cliente autenticado llama la herramienta `context`
- **THEN** el resultado incluye el campo de perfil con disponibilidad e ítems o la marca de no disponible
