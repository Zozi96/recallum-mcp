## MODIFIED Requirements

### Requirement: Confidencialidad de errores MCP
El sistema MUST devolver mensajes estables y seguros para errores esperados, MUST enmascarar el detalle de excepciones inesperadas y de infraestructura, y MUST registrar el diagnóstico sanitizado únicamente del lado servidor sin credenciales ni payloads sensibles. Los fallos inesperados de herramientas y recursos de perfil MUST devolver `internal server error (reference: mcp-<32 caracteres hexadecimales minúsculos>)`, usando una referencia opaca generada por el servidor para esa invocación, presente también en su diagnóstico servidor. La referencia MUST NOT derivarse de identificadores enviados por el cliente, identidad, credenciales ni contenido de memoria y MUST NOT permitir consultar logs mediante una nueva superficie pública. El fallo MUST conservar la forma de error MCP del transporte, nunca una respuesta de éxito. La indisponibilidad del servicio de embeddings en rutas con degradación definida (`remember`, `remember_batch`, `recall`, `context`) MUST NOT producir un error MCP: produce el resultado degradado. El mensaje `embedding service unavailable` queda reservado a operaciones sin degradación definida.

#### Scenario: Fallo inesperado con sentinel interno
- **WHEN** una herramienta lanza una excepción inesperada cuyo mensaje contiene un sentinel interno
- **THEN** la respuesta MCP contiene el mensaje genérico y la referencia opaca, pero no el sentinel, URLs internas, cadenas de conexión ni stack traces

#### Scenario: Referencia localizable
- **WHEN** una herramienta o recurso de perfil devuelve un fallo inesperado con referencia
- **THEN** el operador encuentra el registro sanitizado de ese fallo mediante la misma referencia

#### Scenario: Identificador malicioso y concurrencia
- **WHEN** dos invocaciones concurrentes usan el mismo identificador MCP elegido por el cliente, incluso uno que contiene datos sensibles, y ambas fallan inesperadamente
- **THEN** reciben referencias generadas independientemente que correlacionan sus respectivos registros sin reflejar el identificador recibido ni mezclar los contextos de diagnóstico

#### Scenario: Servicio de embeddings no disponible
- **WHEN** un cliente llama `remember` y el servicio de embeddings no está disponible
- **THEN** el comportamiento pasa a ser el del escenario "Servicio de embeddings no disponible en escritura": resultado exitoso degradado

#### Scenario: Servicio de embeddings no disponible en escritura
- **WHEN** el cliente llama `remember` y el servicio de embeddings no está disponible
- **THEN** el cliente recibe un resultado exitoso con la degradación declarada, no el fallo MCP `embedding service unavailable`

#### Scenario: Servicio de embeddings no disponible en operación sin degradación
- **WHEN** una operación sin degradación definida falla porque el servicio de embeddings no está disponible
- **THEN** el cliente recibe exactamente el mensaje público `embedding service unavailable` y el detalle técnico queda sólo en un log servidor correlacionado

#### Scenario: Error de dominio seguro
- **WHEN** una entrada infringe una regla de dominio cuyo mensaje está clasificado como seguro para cliente
- **THEN** el sistema devuelve ese error accionable sin convertirlo en un fallo interno genérico ni añadirle una referencia

## ADDED Requirements

### Requirement: Descripciones breves y suficientes de herramientas
El servidor MUST mantener las quince herramientas existentes (`remember`, `remember_batch`, `recall`, `context`, `get_memory`, `list_memories`, `update`, `merge_memories`, `related_memories`, `reconfirm`, `forget`, `save_skill`, `match_skills`, `get_skill`, `forget_skill`) y sus esquemas de entrada y salida. Las instrucciones compartidas anunciadas MUST tener como máximo 1.400 caracteres Unicode y cada descripción de herramienta anunciada MUST tener como máximo 1.600. Cada descripción MUST expresar propósito, criterio de elección frente a operaciones próximas y un ejemplo mínimo válido; MUST conservar las advertencias aplicables a esa operación aun cuando el cliente no muestre las instrucciones compartidas. No se exige que un cliente externo deje de repetir instrucciones.

#### Scenario: Catálogo completo
- **WHEN** un cliente autenticado descubre las herramientas
- **THEN** recibe exactamente los quince nombres con los esquemas previos, todas las descripciones cumplen el límite y sus ejemplos usan argumentos válidos del esquema correspondiente

#### Scenario: Herramientas de escritura sin guía compartida
- **WHEN** un cliente sólo presenta al agente las descripciones de `remember`, `remember_batch`, `update`, `merge_memories` y `save_skill`
- **THEN** cada operación que introduce contenido conserva la advertencia de pedir autorización antes de persistir información sensible; las operaciones con `similar` explican su revisión y las distinciones de sustitución, fusión y reemplazo siguen visibles donde aplican

#### Scenario: Operaciones próximas distinguibles
- **WHEN** el agente compara `recall` con `match_skills`, `get_memory` con `list_memories`, o `reconfirm` con `update` y `merge_memories`
- **THEN** las descripciones distinguen memorias de procedimientos, lectura puntual de enumeración y verificación sin reescritura de corrección o consolidación; las contradicciones no se presentan como fusiones automáticas

#### Scenario: Orientación detallada accesible
- **WHEN** el agente necesita el ciclo completo de captura o revisión de memorias
- **THEN** las instrucciones compartidas remiten a los prompts existentes y a la guía del plugin, sin añadir prompts ni herramientas y sin retirar las salvaguardas mínimas locales

### Requirement: Ejemplos de recuperación con ámbito e identificadores
La documentación de clientes y la guía distribuida MUST incluir ejemplos mínimos válidos de `recall` para proyecto con globales, sólo proyecto, sólo globales, filtro por `symbol` y filtro por `file`. MUST explicar que `scope='project'` requiere `project`, que las anclas filtran antes del ranking y que una consulta textual sin ancla permite buscar menciones no ancladas. MUST distinguir recuperar un identificador de memoria con `get_memory` de buscar un símbolo. Los ejemplos MUST consultar en inglés sin inventar claves canónicas ni traducir identificadores. La descripción breve de `recall` MUST incluir al menos el ejemplo habitual de proyecto con globales y las advertencias sobre idioma, ámbito y anclas.

#### Scenario: Matriz de ámbitos
- **WHEN** una guía presenta una búsqueda de proyecto con globales, sólo proyecto o sólo globales
- **THEN** muestra respectivamente `project=P` sin `scope`, `project=P` con `scope='project'` y `scope='global'` sin `project`, donde P es la clave canónica obtenida para el workspace

#### Scenario: Filtro de ancla y búsqueda textual
- **WHEN** una guía muestra `symbol` o `file`
- **THEN** explica que una lista vacía puede significar ausencia de anclas coincidentes y muestra la variante que omite ese filtro manteniendo el identificador literal en `query`, sin ordenar llamadas adicionales automáticas en toda búsqueda

#### Scenario: UUID conocido
- **WHEN** la intención es leer una memoria por su UUID conocido
- **THEN** la guía indica `get_memory(memory_id=...)` y no presenta `symbol` como filtro por UUID de memoria
