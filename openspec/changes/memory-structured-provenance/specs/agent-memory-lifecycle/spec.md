## ADDED Requirements

### Requirement: Procedencia estructurada opcional
Cada memoria MUST poder llevar `source_type` (`agent`, `user`, `bootstrap`, `unknown`) y un `source_ref` opcional (texto corto: ruta, commit, identificador de archivo o equivalente). Ausencia de ambos MUST interpretarse como `unknown` / nulo. `source_ref` MUST NOT usarse para almacenar transcripts, prompts ni logs. El sistema MUST NOT introducir un nivel de almacenamiento de conversación RAW.

#### Scenario: Guardar con procedencia
- **WHEN** un usuario llama `remember` con `source_type=agent` y `source_ref` apuntando a un archivo del repo
- **THEN** las lecturas posteriores incluyen esos campos

#### Scenario: Filas existentes
- **WHEN** se lee una memoria creada antes de este change
- **THEN** `source_type` es `unknown` y `source_ref` es nulo

#### Scenario: Rechazo de transcript
- **WHEN** `source_ref` o el contenido intentan persistir una conversación completa
- **THEN** siguen aplicando las reglas ya existentes de contenido atómico; este change no añade un almacén de conversaciones

### Requirement: Trazabilidad sólo por supersesión
El único enlace padre/hijo entre memorias MUST seguir siendo `superseded_by` (update/merge) y la historia recuperable con `get_memory(include_history=true)`. El sistema MUST NOT crear tablas por nivel (CORE/CONTEXT/FACT/RAW) ni un grafo `derived_from` adicional.

#### Scenario: Corrección
- **WHEN** una memoria se sustituye con `update` de contenido
- **THEN** la fila retirada apunta a la reemplazo y la historia la enumera, como hoy

#### Scenario: Sin niveles de pirámide
- **WHEN** un cliente solicita un “nivel” CORE o RAW
- **THEN** no existe tal dimensión de almacenamiento; el perfil materializado sigue siendo la proyección de alta densidad ya especificada
