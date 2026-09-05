## MODIFIED Requirements

### Requirement: Observabilidad HTTP segura
El sistema MUST correlacionar cada petición con un request ID y MUST observar únicamente método, plantilla de ruta, status y latencia mediante campos de baja cardinalidad. La superficie de métricas operativas MUST estar protegida contra exposición pública accidental con el mismo rigor que los endpoints de salud y MUST NOT exponer etiquetas derivadas de query, UUID, cookie, token, correo o contenido de memoria.

#### Scenario: Petición normal
- **WHEN** una petición atraviesa FastAPI o FastMCP
- **THEN** la respuesta contiene un request ID y el evento servidor registra método, plantilla, status y latencia

#### Scenario: Datos sensibles presentes
- **WHEN** URL, headers o cuerpo contienen query, UUID, cookie, token, correo o contenido de memoria
- **THEN** logs y métricas HTTP no contienen esos valores ni crean etiquetas derivadas de ellos

#### Scenario: Request ID no confiable
- **WHEN** el cliente envía un request ID fuera del alfabeto o longitud permitidos
- **THEN** el sistema lo reemplaza por uno generado y acotado

#### Scenario: Superficie de métricas no pública
- **WHEN** un cliente no operador intenta acceder a la superficie de métricas
- **THEN** el acceso es rechazado con el mismo criterio que un endpoint protegido, sin filtrar etiquetas sensibles en la negativa
