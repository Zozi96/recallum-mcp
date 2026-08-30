## MODIFIED Requirements

### Requirement: Densidad útil de resultados recuperados
El sistema MUST tratar `limit` y `max_tokens` como límites máximos de `recall` y de los candidatos recuperados por `context(focus=...)`, y MUST poder devolver menos ítems que el límite solicitado. MUST NOT completar esos techos con un reranker ni con un contador de tokens remoto. MUST conservar memorias de soporte o contexto que aporten valor aunque no sean la respuesta esencial, y MUST mantener el aislamiento, los filtros y los presupuestos existentes.

El sistema MAY aplicar un piso de similitud coseno sólo a la pierna vectorial de la recuperación híbrida. Ese piso MUST NOT aplicarse a las piernas textuales. Una memoria admitida por cualquier pierna válida MUST poder participar en la fusión. El resultado fusionado MUST NOT presentarse como conjunto de únicamente memorias con utilidad calibrada: coincidencias léxicas y vecinos vectoriales pueden incluir ruido temático.

Cuando ningún piso vectorial está configurado, el sistema MUST conservar en la pierna vectorial el pool de vecinos más cercanos aunque su similitud absoluta sea débil. Esa ausencia de piso MUST ser el valor por defecto de producción. La configuración por defecto MUST estar respaldada por el evaluador versionado, incluyendo el caso en que ningún umbral candidato reduce el ruido medido sin degradar las etiquetas protegidas. MUST NOT elegir un umbral de producción por intuición. MUST NOT exponer el piso como argumento de las herramientas del agente.

Cuando un piso vectorial sí está configurado, el sistema MUST excluir de la pierna vectorial las memorias por debajo del umbral. MUST NOT tratar ese piso como admisión global: una memoria por debajo del umbral vectorial MUST poder aparecer si una pierna textual la admite.

En degradación textual, el sistema MUST aplicar sólo los predicados textuales vigentes, MUST marcar el modo degradado donde corresponda y MUST NOT rellenar el límite con memorias sin coincidencia textual válida.

#### Scenario: Default sin piso vectorial
- **WHEN** no hay un piso de similitud vectorial configurado y existen vecinos cercanos de similitud absoluta débil
- **THEN** `recall` y `context(focus=...)` pueden incluirlos, y ese default es el respaldado por el evaluador versionado

#### Scenario: El límite no se rellena con ruido
- **WHEN** un piso vectorial está configurado, una memoria es vecina cercana pero queda por debajo del umbral y no coincide en las piernas textuales, y el usuario llama `recall` con un `limit` mayor que el número de ítems admitidos
- **THEN** esa memoria no aparece y el sistema no completa el límite con ella

#### Scenario: Sin memoria útil
- **WHEN** ninguna memoria activa y visible coincide en las piernas textuales ni supera un piso vectorial configurado (o los embeddings no están disponibles y no hay coincidencia textual)
- **THEN** `recall` devuelve una lista vacía

#### Scenario: Piso vectorial no silencia coincidencia textual
- **WHEN** un piso vectorial está configurado y una memoria temáticamente cercana pero irrelevante coincide en una pierna textual
- **THEN** esa memoria puede aparecer en el resultado fusionado

#### Scenario: Contexto de soporte conservado
- **WHEN** una memoria responde directamente a la consulta y otra memoria aporta una restricción, consecuencia o procedimiento relevante dentro del presupuesto
- **THEN** ambas pueden aparecer en el resultado, ordenadas por la recuperación vigente, sin exigir que todo ítem sea una respuesta directa

#### Scenario: Foco de contexto usa la misma admisión
- **WHEN** `context` se llama con `focus` y un piso vectorial está configurado
- **THEN** los candidatos enfocados que sólo entrarían por la pierna vectorial y quedan bajo el umbral no se incorporan a los grupos, mientras el perfil y la selección por importancia continúan bajo sus reglas existentes

#### Scenario: Degradación textual conserva utilidad
- **WHEN** los embeddings no están disponibles durante `recall` o `context(focus=...)`
- **THEN** el sistema aplica la admisión sobre las señales textuales disponibles, marca el modo degradado donde corresponda y no rellena el límite con memorias sin coincidencia textual válida

#### Scenario: El agente no elige el piso
- **WHEN** un agente llama `recall` o `context`
- **THEN** no puede pasar un piso de similitud vectorial; sólo la configuración del servidor (o un override administrativo de evaluación) lo controla
