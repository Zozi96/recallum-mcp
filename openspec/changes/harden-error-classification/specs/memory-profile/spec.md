## MODIFIED Requirements

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
