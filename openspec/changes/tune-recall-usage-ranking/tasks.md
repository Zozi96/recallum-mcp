## 1. Dataset y evaluador

- [x] 1.1 Asegurar dataset versionado de ranking con tags y expected keys
- [x] 1.2 Documentar comando de evaluación (MRR, recall@k, misses) separado del workflow evaluator

## 2. Fusión de uso

- [x] 2.1 Verificar/implementar voto de uso en fusión de `recall` respetando `recall_usage_weight` y cota frente a señales primarias
- [x] 2.2 Confirmar default 0.0 y aislamiento por usuario en pruebas

## 3. Experimento

- [x] 3.1 Correr baseline (peso 0) y al menos un peso candidato > 0 contra el dataset
- [x] 3.2 Documentar resultado y decisión de no cambiar (o diferir) el default de producción

## 4. Verificación

- [x] 4.1 Tests unitarios de fusión con peso 0 vs > 0
- [x] 4.2 Suite de evaluación de ranking en seco reproducible
