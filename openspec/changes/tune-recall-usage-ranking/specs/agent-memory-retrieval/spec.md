## ADDED Requirements

### Requirement: Evaluación reproducible de ranking
El proyecto MUST proporcionar un dataset versionado y un evaluador de ranking (MRR, recall@k, misses por etiqueta) distinto del evaluador de flujo de checkpoints. El dataset MUST usar corpus e identificadores sintéticos o de fixture, MUST NOT requerir contenido de producción, y MUST permitir comparar tunables de fusión de forma reproducible.

#### Scenario: Informe de ranking
- **WHEN** el operador ejecuta el evaluador de ranking contra el dataset versionado
- **THEN** obtiene MRR, recall@k y la lista de misses sin mezclar métricas del flujo de checkpoints

#### Scenario: Comparar tunables
- **WHEN** se ejecuta el mismo dataset con dos configuraciones de fusión
- **THEN** el informe expone ambas y permite ver si MRR/recall@k mejoran sin fabricar empates

### Requirement: Voto de uso en la fusión de recall
La fusión de `recall` MUST poder incorporar un voto derivado del uso registrado (`recall_count` / señales de servicio ya persistidas) mediante un peso configurable. El valor por defecto MUST ser 0.0 (sin efecto). Un peso mayor que cero MUST NOT activarse como default de producción sin un experimento documentado que compare el baseline (peso 0) usando el evaluador de ranking. El voto de uso MUST NOT superar la fuerza de una señal de recuperación primaria, MUST respetar aislamiento por usuario, y MUST seguir aplicando en modo degradado sólo sobre candidatos textuales válidos.

#### Scenario: Default sin efecto
- **WHEN** `recall_usage_weight` está en 0.0
- **THEN** el orden de `recall` coincide con la fusión de relevancia/importancia vigente sin reordenar por uso

#### Scenario: Peso positivo medido
- **WHEN** un operador configura un peso de uso > 0 tras comparar el dataset de ranking
- **THEN** memorias con mayor uso pueden desempatar o reordenar candidatos ya cercanos en relevancia, sin desalojar un match claramente mejor

#### Scenario: Aislamiento intacto
- **WHEN** la fusión aplica el voto de uso
- **THEN** sólo participan memorias activas del usuario autenticado
