## MODIFIED Requirements

### Requirement: Confidencialidad de errores MCP
El sistema MUST devolver mensajes estables y seguros para errores esperados, MUST enmascarar el detalle de excepciones inesperadas y de infraestructura, y MUST registrar el diagnóstico completo únicamente del lado servidor sin credenciales ni payloads sensibles. La indisponibilidad del servicio de embeddings en rutas con degradación definida (`remember`, `remember_batch`, `recall`, `context`) MUST NOT producir un error MCP: produce el resultado degradado. El mensaje `embedding service unavailable` queda reservado a operaciones sin degradación definida.

#### Scenario: Fallo inesperado con sentinel interno
- **WHEN** una herramienta lanza una excepción inesperada cuyo mensaje contiene un sentinel interno
- **THEN** la respuesta MCP indica un fallo genérico y no contiene el sentinel, URLs internas, cadenas de conexión ni stack traces

#### Scenario: Servicio de embeddings no disponible
- **WHEN** un cliente llama `remember` y el servicio de embeddings no está disponible
- **THEN** el comportamiento pasa a ser el del escenario "Servicio de embeddings no disponible en escritura": resultado exitoso degradado

#### Scenario: Servicio de embeddings no disponible en escritura
- **WHEN** un cliente llama `remember` y el servicio de embeddings no está disponible
- **THEN** el cliente recibe un resultado exitoso con la degradación declarada, no el fallo MCP `embedding service unavailable`

#### Scenario: Servicio de embeddings no disponible en operación sin degradación
- **WHEN** una operación sin degradación definida falla porque el servicio de embeddings no está disponible
- **THEN** el cliente recibe exactamente el mensaje público `embedding service unavailable` y el detalle técnico queda sólo en un log servidor correlacionado

#### Scenario: Error de dominio seguro
- **WHEN** una entrada infringe una regla de dominio cuyo mensaje está clasificado como seguro para cliente
- **THEN** el sistema devuelve ese error accionable sin convertirlo en un fallo interno genérico
