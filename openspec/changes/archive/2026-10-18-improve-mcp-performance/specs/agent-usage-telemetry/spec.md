## ADDED Requirements

### Requirement: Visibilidad operativa del cache de identidad y del uso diferido
La superficie de métricas operativas MUST exponer, de forma agregada y anónima, los aciertos y fallos del cache de identidad de autenticación y los descartes por acotación y fallos de aplicación del registro de uso diferido de memorias servidas. Esa exposición MUST NOT contener hashes de claves, contenido de memoria, datos de usuario ni etiquetas derivadas de valores sensibles.

#### Scenario: Hit rate de identidad observable
- **WHEN** se autentican peticiones MCP y el operador consulta la superficie de métricas
- **THEN** puede calcular la proporción de autenticaciones servidas desde el cache de identidad sin leer los logs

#### Scenario: Descarte de uso diferido observable
- **WHEN** el registro de uso pendiente descarta eventos por acotación o falla al aplicarse y el operador consulta la superficie de métricas
- **THEN** el descarte o el fallo es observable sin leer los logs y sin exponer a qué usuario o memoria correspondía

#### Scenario: Sin material de claves
- **WHEN** se inspecciona la superficie de métricas
- **THEN** no contiene claves, hashes de claves, correos ni identificadores de memorias o de usuarios
