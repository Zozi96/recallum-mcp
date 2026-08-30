## 1. Métricas de diagnóstico

- [ ] 1.1 Añadir `explicit-zero-rate@5` y `unjudged-rate@5` al evaluador y al informe (globales, por etiqueta y por consulta) sin cambiar `irrelevant-rate@5`, y verificar con `uv run pytest tests/unit/test_evaluation.py tests/unit/test_cli.py` que undeclared cuenta en irr, sólo en unjudged, y el explícito 0 cuenta en ambos irr y explicit-zero.
- [ ] 1.2 Cubrir consultas heredadas sin `relevance` (métricas nuevas `n/a`) y el caso mixto del spec (un explícito 0 y un undeclared en el top-5) mediante `uv run pytest tests/unit/test_evaluation.py`.

## 2. Dataset denso

- [ ] 2.1 Registrar en `openspec/changes/recalibrate-memory-admission-default/experiment-record.md` el ranking baseline (`k=10`, Vmin unset) usado para densificar, reutilizando el dump de 2026-08-30 o una corrida throwaway nueva reproducible.
- [ ] 2.2 Ampliar `relevance` en `scripts/eval_dataset.json` para cada clave servida en ese baseline y los negativos difíciles del mismo tema, con grados 0–3 temáticos (no promover ruido a 3), y verificar carga y las cuatro direcciones de idioma con `uv run pytest tests/unit/test_evaluation.py`.
- [ ] 2.3 Añadir una aserción de dataset (prueba unitaria sobre el JSON más el ranking registrado, o un chequeo del evaluador) que falle si alguna clave del top-k baseline carece de juicio, de modo que `unjudged-rate@5` del dataset versionado sea 0.0; verificar con `uv run pytest tests/unit/test_evaluation.py`.

## 3. Recalibración del default

- [ ] 3.1 Ejecutar baseline + matriz Vmin en Postgres/Ollama desechables con el dataset denso, mismos tunables y guardas que `improve-memory-context-precision`, y adjuntar métricas (incluidas explicit-zero y unjudged) en el expediente de este change.
- [ ] 3.2 Si un umbral pasa las guardas, ponerlo como default de `recall_vector_min_similarity` y fijarlo con una prueba; si ninguno pasa, dejar `None`, documentar el segundo bloqueo y no tocar FTS/trigram. Verificar con `uv run pytest tests/unit/test_service.py`.

## 4. Validación y cierre

- [ ] 4.1 Ejecutar `uv run pytest tests/unit` y `uv run pytest tests/integration` y conservar el resumen.
- [ ] 4.2 Ejecutar `uv run ruff check recallum tests` y `openspec validate recalibrate-memory-admission-default --strict`.
- [ ] 4.3 Archivar juntos `improve-memory-context-precision` y este change sólo después de 3.2 (default activado o segundo bloqueo documentado).
