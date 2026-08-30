## 1. Evaluación de utilidad contextual

- [x] 1.1 Extender el loader del dataset con juicios opcionales `relevance: 0..3`, conservar `expect` y marcar como no disponibles las métricas graduadas de consultas heredadas sin juicios, y verificar con pruebas unitarias casos válidos, grados fuera de rango, claves desconocidas y datasets heredados mediante `uv run pytest tests/unit/test_evaluation.py`.
- [x] 1.2 Implementar `nDCG@5`, `essential-recall@3`, `irrelevant-rate@5` y densidad de tokens útiles como cálculos puros, cubriendo respuestas completas, cortas, vacías y con negativos mediante `uv run pytest tests/unit/test_evaluation.py`.
- [x] 1.3 Ampliar el informe global, por etiqueta y por consulta sin alterar las líneas heredadas de MRR/recall@k, y verificar snapshots/aserciones de rendering con `uv run pytest tests/unit/test_evaluation.py tests/unit/test_cli.py`.
- [x] 1.4 Ampliar `scripts/eval_dataset.json` con memorias sintéticas grado 1/2, negativos difíciles lexicales/semánticos y juicios para todas las etiquetas existentes, y verificar carga, conteos y cobertura de las cuatro direcciones español/inglés con `uv run pytest tests/unit/test_evaluation.py`.

## 2. Admisión vectorial antes de fusión

- [x] 2.1 Añadir `recall_vector_min_similarity` a los límites/configuración y al override administrativo de evaluación, con estado desactivado compatible y validación acotada `0..1`; verificar defaults, límites y CLI mediante `uv run pytest tests/unit/test_service.py tests/unit/test_cli.py`.
- [x] 2.2 Aplicar el umbral en la consulta vectorial junto con visibilidad, modelo, filtros y orden HNSW existentes, y verificar en los contratos de repositorio que vecinos por debajo del umbral se excluyen sin afectar FTS/trigram, RLS, anclas ni proyectos mediante `uv run pytest tests/integration/test_db.py`.
- [x] 2.3 Propagar el umbral a `recall` y a los pools de `context(focus=...)` sin cambiar RRF, strategy, presupuestos ni el perfil; verificar resultados por debajo de `limit`, resultados vacíos, soporte admitido y perfil intacto mediante `uv run pytest tests/unit/test_service.py tests/unit/test_memory_profile.py`.
- [x] 2.4 Cubrir el modo sin embeddings para demostrar que FTS/trigram siguen sirviendo coincidencias válidas sin rellenar con ruido vectorial y que `recall` conserva `mode=degraded_textual`; verificar con `uv run pytest tests/unit/test_service.py tests/integration/test_db.py`.
- [x] 2.5 Confirmar que el esquema MCP no cambia y documentar que `limit` es un máximo; verificar herramientas/documentación y respuestas cortas con `uv run pytest tests/unit/test_mcp_tools.py tests/unit/test_mcp_tools_docs.py`.

## 3. Calibración reproducible del default

- [x] 3.1 Ejecutar el baseline real-stack con admisión desactivada sobre un usuario/database desechables y registrar modelo, dataset, tunables, métricas globales y por etiqueta en `openspec/changes/improve-memory-context-precision/experiment-record.md`; verificar que dos ejecuciones desde el mismo estado producen informes idénticos.
- [x] 3.2 Ejecutar una matriz acotada de candidatos para `recall_vector_min_similarity` sobre el mismo estado, modelo y dataset, y registrar `essential-recall@3`, `nDCG@5`, `irrelevant-rate@5` y densidad útil global y multilingüe en el mismo expediente.
- [x] 3.3 Seleccionar el menor umbral que reduzca irrelevantes sin degradar ninguna guarda y verificar que el valor coincide con el expediente y una prueba fija el default; si ninguno cumple, conservarlo desactivado, documentar el bloqueo y volver al diseño sin completar ni archivar el cambio.

## 4. Validación integral y entrega

- [x] 4.1 Ejecutar `uv run pytest tests/unit` y `uv run pytest tests/integration`, corregir cualquier regresión y conservar la salida resumida de ambos comandos.
- [x] 4.2 Ejecutar `uv run ruff check recallum tests` y `openspec validate improve-memory-context-precision --strict`, corrigiendo todo fallo antes de marcar el cambio listo.
- [x] 4.3 Revisar adversarialmente consultas sin match, exactas, typo, identificadores, soporte contextual, negativos difíciles, filtros, presupuestos y las cuatro direcciones de idioma; verificar que cada escenario de `specs/agent-memory-retrieval/spec.md` queda cubierto por una prueba o por el expediente real-stack.
