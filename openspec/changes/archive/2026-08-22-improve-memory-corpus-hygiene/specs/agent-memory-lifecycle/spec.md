## ADDED Requirements

### Requirement: Reconciliación guiada ante similares
Cuando `remember` o `remember_batch` reportan similares, la guía del sistema (skill, prompts o documentación de agente) MUST distinguir: reexpresiones o refinamientos del mismo claim → `merge_memories`; hecho incorrecto u obsoleto → `update` del incorrecto; contradicción entre claims vigentes → `update` o `forget` del incorrecto tras verificación humana/agente, NEVER un merge que “resuelva” la contradicción. El servidor MUST NOT auto-merge ni auto-olvidar por el aviso de similares.

#### Scenario: Reexpresión del mismo claim
- **WHEN** los similares restatan el mismo claim subyacente con distinta redacción
- **THEN** la guía vigente indica consolidar con `merge_memories` y no crear otra copia vía `remember`

#### Scenario: Contradicción
- **WHEN** un similar afirma lo opuesto o incompatible
- **THEN** la guía vigente indica verificar y corregir con `update` o `forget`, y prohíbe usar `merge_memories` para resolver la contradicción

#### Scenario: Servidor no decide
- **WHEN** existen similares al guardar
- **THEN** la memoria nueva (o deduplicada) se persiste según las reglas actuales y el aviso permanece informativo sin mutar las similares

### Requirement: Desenlace explícito de la cola stale
La guía de higiene MUST exigir que cada memoria stale revisada termine en un desenlace explícito: `reconfirm` si sigue siendo cierta, `update` si cambió, `forget` si ya no aplica, o `merge_memories` si es reexpresión de otra activa. MUST NOT dejar la revisión en “ya la vi” sin una de esas acciones cuando la verificación concluyó.

#### Scenario: Stale aún cierta
- **WHEN** el agente verifica una memoria stale que sigue siendo verdadera
- **THEN** la guía exige `reconfirm` y no un `remember` idéntico

#### Scenario: Stale falsa
- **WHEN** el agente verifica una memoria stale que ya no es cierta
- **THEN** la guía exige `update` o `forget` según corresponda

#### Scenario: Stale duplicada
- **WHEN** varias stale o activas restatan el mismo claim
- **THEN** la guía exige `merge_memories` hacia una sola formulación en inglés
