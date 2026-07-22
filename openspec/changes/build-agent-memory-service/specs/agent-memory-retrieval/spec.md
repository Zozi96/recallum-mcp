## ADDED Requirements

### Requirement: Búsqueda híbrida de memorias
El sistema MUST recuperar memorias mediante señales vectoriales y textuales, aplicando aislamiento de usuario antes de ordenar los resultados.

#### Scenario: Recuperar por significado
- **WHEN** un usuario llama `recall` con una consulta semánticamente relacionada pero con palabras diferentes
- **THEN** el sistema puede devolver sus memorias vectorialmente relevantes dentro del límite solicitado

#### Scenario: Recuperar término exacto
- **WHEN** una consulta contiene un término técnico exacto presente en una memoria
- **THEN** la señal textual participa en el orden de relevancia del resultado

#### Scenario: Consulta sin resultados
- **WHEN** ninguna memoria activa del usuario satisface la consulta y los filtros
- **THEN** el sistema devuelve una lista vacía sin incluir memorias de otros usuarios

### Requirement: Filtros de recuperación
El sistema MUST permitir filtrar recuperación por ámbito global, proyecto y categoría sin aceptar un identificador de usuario proporcionado por el cliente.

#### Scenario: Recuperar contexto de proyecto
- **WHEN** un usuario consulta un proyecto concreto
- **THEN** el sistema considera sus memorias globales y las memorias de ese proyecto, excluyendo las de proyectos distintos

#### Scenario: Recuperar sólo decisiones
- **WHEN** un usuario filtra `recall` por la categoría `decision`
- **THEN** el sistema devuelve únicamente decisiones activas del ámbito solicitado

### Requirement: Contexto compacto de sesión
El sistema MUST generar contexto compacto con memorias globales y del proyecto respetando límites de cantidad y caracteres.

#### Scenario: Iniciar sesión de proyecto
- **WHEN** un agente llama `context` con un proyecto válido
- **THEN** el sistema devuelve preferencias globales y memorias relevantes de ese proyecto ordenadas y agrupadas por categoría

#### Scenario: Respetar el presupuesto de contexto
- **WHEN** existen más memorias relevantes que las permitidas por los límites solicitados
- **THEN** el sistema trunca por relevancia sin exceder el máximo de elementos ni caracteres

### Requirement: Degradación textual
El sistema MUST mantener búsquedas textuales disponibles cuando PostgreSQL funciona pero Ollama no puede generar el embedding de una consulta.

#### Scenario: Ollama no disponible durante recall
- **WHEN** el servicio de embeddings falla al procesar una consulta
- **THEN** `recall` devuelve resultados textuales marcando el modo degradado en la respuesta
