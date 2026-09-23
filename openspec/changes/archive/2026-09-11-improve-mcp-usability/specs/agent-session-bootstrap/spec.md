## ADDED Requirements

### Requirement: Guía práctica de búsqueda independiente del idioma de conversación
La skill y la regla de memoria distribuidas con el plugin MUST enseñar al agente a expresar la intención de `recall.query` en inglés aunque la conversación use otro idioma, preservando literalmente comandos, rutas, símbolos y términos definidos por el usuario. MUST usar la clave canónica del workspace y los nombres de herramienta visibles para el cliente. La guía MUST incluir los ejemplos de ámbito y anclas del contrato MCP y MUST conservar `limit=3` en los ejemplos de checkpoint, la supresión de consultas redundantes y la continuidad fail-open. Esta orientación MUST NOT añadir traducción en el servidor ni ordenar reescribir memorias existentes por su idioma.

#### Scenario: Pregunta en español con un símbolo
- **WHEN** el usuario pregunta «¿qué decidimos sobre MemoryService.context?»
- **THEN** la guía muestra una consulta como `What did we decide about MemoryService.context?`, con el símbolo intacto, la clave canónica aplicable y la respuesta al usuario en su idioma

#### Scenario: Ruta y comando literales
- **WHEN** la intención de búsqueda contiene `recallum/memory/service.py` y `uv run pytest`
- **THEN** la traducción indicada conserva exactamente ambos identificadores dentro de la consulta inglesa

#### Scenario: Distribución coherente
- **WHEN** se leen la skill, la regla y la guía de clientes distribuidas
- **THEN** los ejemplos de proyecto, globales, anclas e idioma tienen la misma semántica y no sustituyen las instrucciones actuales del usuario por recuerdos

#### Scenario: Checkpoint suficiente o servicio ausente
- **WHEN** el contexto activo ya cubre la decisión siguiente o las herramientas Recallum no están disponibles
- **THEN** los nuevos ejemplos no ordenan una consulta redundante ni bloquean la tarea, conservando la política de checkpoint y fail-open existente
