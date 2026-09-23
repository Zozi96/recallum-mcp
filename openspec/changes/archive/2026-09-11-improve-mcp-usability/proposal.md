## Why

Recallum entrega contexto y orientación difíciles de aprovechar: el perfil reservado puede desplazar recuerdos pertinentes con hechos de otros temas, las descripciones visibles repiten instrucciones extensas y buscar exige conocer convenciones de idioma y ámbito. Además, un fallo inesperado sólo devuelve `internal server error`, sin una referencia que permita localizarlo en el diagnóstico servidor.

## What Changes

- **BREAKING (selección, no esquema):** limitar `profile.static` a preferencias y restricciones activas. Los hechos y decisiones siguen almacenados y recuperables, pero su importancia no les concede una plaza permanente. En `context(focus=...)`, servir `dynamic=[]` y recuperar los demás recuerdos por las rutas existentes de foco e importancia; sin foco y en el recurso de perfil, conservar el dynamic por uso reciente.
- Simplificar las instrucciones compartidas y las descripciones de las quince herramientas existentes, con ejemplos mínimos y límites de longitud verificables. Conservar las advertencias de seguridad y las diferencias entre operaciones; no añadir herramientas.
- Enseñar llamadas mínimas de `recall` para proyecto más globales, sólo proyecto, sólo globales y anclas. La guía del plugin debe convertir la intención de búsqueda al inglés preservando identificadores; el servidor no incorpora traducción ni cambia los filtros.
- Añadir una referencia opaca generada por el servidor al error inesperado público y al registro sanitizado correspondiente, reutilizando la infraestructura de diagnóstico. Mantener los mensajes de dominio, la degradación de embeddings y el aislamiento de usuario.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `memory-profile`: elegibilidad estática, excepción de dynamic para contexto con foco y renovación de perfiles derivados existentes.
- `agent-memory-retrieval`: reserva de perfil sólo estático cuando hay foco, presupuesto, deduplicación y compatibilidad sin foco.
- `mcp-agent-integration`: descripciones breves de las quince herramientas, ejemplos de búsqueda y errores inesperados con referencia segura.
- `agent-session-bootstrap`: guía de búsqueda en inglés con ejemplos de ámbito y anclas en el plugin distribuido.

## Impact

- Perfil y recuperación: `recallum/memory/profile_select.py`, `recallum/memory/service.py`, `recallum/db/repositories/memory_repo.py`, configuración de límites y una migración de invalidación de `memory_profiles` derivados.
- Superficie MCP: `recallum/mcp/server.py`, `recallum/mcp/errors.py` y pruebas existentes de herramientas, recursos y diagnóstico. La forma de éxito, nombres y esquemas de argumentos permanecen iguales; cambia el texto de los fallos inesperados para incorporar la referencia.
- Distribución: skill y regla de memoria bajo `plugins/recallum-memory/`, documentación de clientes y operaciones, y sus comprobaciones contractuales. No se editan instalaciones personales de clientes.
- Sin dependencias, servicios de traducción, cambios en ranking híbrido, identidad, almacenamiento de memorias fuente ni interfaz web. La observación de ruido motiva el cambio, pero no demuestra una fuga de aislamiento ni una regresión de ranking.
