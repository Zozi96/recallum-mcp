## Context

See `proposal.md` for motivation and `specs/agent-memory-retrieval/spec.md` for the behavior contract.

La recuperación actual obtiene hasta 60 candidatos por señal, fusiona posiciones mediante RRF y empaqueta el prefijo según ítems/tokens. FTS ya exige una coincidencia `tsvector`; trigram ya exige `word_similarity` mínimo; la búsqueda vectorial, en cambio, devuelve los vecinos más cercanos aunque su similitud absoluta sea débil. RRF sólo conoce posiciones y no puede distinguir “mejor vecino disponible” de “memoria suficientemente relevante”. `context(focus=...)` reutiliza los mismos pools, mientras que el perfil materializado y la selección por importancia tienen contratos distintos y no deben someterse a este filtro de foco.

El evaluador actual conserva `expect`, MRR y recall@k sobre un dataset pequeño. No existe una señal que penalice la cola irrelevante ni que distinga una respuesta esencial de contexto de soporte.

## Goals / Non-Goals

**Goals:**

- Evitar que la pierna vectorial introduzca candidatos sin evidencia mínima antes de RRF.
- Permitir resultados más cortos sin perder memorias de soporte con utilidad medida.
- Calibrar el default con juicios graduados, negativos difíciles y guardas multilingües.
- Reutilizar la recuperación, configuración y estimación de tokens existentes.

**Non-Goals:**

- Añadir reranking con LLM, traducción automática, otro vector store o una dependencia nueva.
- Filtrar el bloque de perfil o las memorias añadidas por importancia sin `focus`.
- Limpiar, reclasificar o migrar el corpus real existente.
- Cambiar los pesos por defecto de importancia, uso, frescura o trigram.
- Optimizar latencia de embeddings, reconstrucción de perfiles o telemetría.

## Decisions

### 1. Admitir cada señal antes de RRF

La consulta vectorial aplicará un `recall_vector_min_similarity` propiedad del servidor junto con el filtro de modelo, visibilidad, categoría, `kind` y anclas. FTS y trigram conservarán sus predicados actuales. La unión de los pools admitidos seguirá entrando en el mismo RRF; si una memoria es admitida por cualquier pierna válida puede participar y recibir los votos secundarios existentes.

```text
embedding ── cosine >= Vmin ─┐
FTS ──────── match actual ───┼──▶ RRF actual ─▶ strategy ─▶ presupuesto
trigram ──── threshold actual┘
```

El umbral se aplicará en la consulta PostgreSQL, no después de traer vecinos débiles. Así no se añade un round trip ni se inventa una segunda capa de ranking.

Alternativas descartadas:

- Umbral sobre el score RRF: las posiciones no expresan relevancia absoluta y cambian según qué piernas encuentren candidatos.
- Acuerdo obligatorio entre dos piernas: eliminaría matches semánticos y multilingües que sólo puede encontrar la pierna vectorial.
- Reranker LLM: añade latencia, coste, dependencia y no determinismo antes de agotar las señales ya instaladas.

### 2. `limit` sigue siendo API-compatible y deja de ser objetivo de relleno

No se añaden campos ni argumentos MCP. `limit` y `max_tokens` continúan siendo máximos; la admisión puede reducir el pool y por ello el resultado final puede contener menos ítems. `score` continúa siendo el score RRF, no se redefine como probabilidad de relevancia.

En `context(focus=...)`, sólo los pools derivados de `focus` pasan por la nueva admisión. El perfil, los grupos por importancia, los conteos de omitidos y sus presupuestos conservan el comportamiento vigente.

Alternativa descartada: exponer `min_similarity` al agente. Haría que clientes no calibrados pudieran desactivar la política de precisión y convertiría un detalle dependiente del modelo en contrato público.

### 3. Calibrar el default mediante una selección reproducible

El evaluador aceptará un override del umbral para comparar el baseline sin admisión vectorial con candidatos. El default de producción será el umbral más bajo que, sobre el mismo dataset y modelo:

1. no reduzca `essential-recall@3` ni `nDCG@5` global o en las etiquetas multilingües protegidas;
2. reduzca `irrelevant-rate@5`; y
3. no reduzca la proporción de tokens útiles.

Si ningún candidato cumple las guardas, el default permanecerá desactivado, el requisito de admisión se considerará no satisfecho y la implementación se detendrá para revisar el diseño antes de completar o archivar el cambio; no se elegirá un valor por intuición. Entre candidatos equivalentes se elige el umbral menor para favorecer contexto de soporte.

La configuración queda asociada operacionalmente al modelo de embeddings: cambiar de modelo exige repetir el experimento antes de conservar el mismo valor.

### 4. Extender el dataset sin romper `expect`

Cada consulta podrá declarar un mapa opcional `relevance` de clave de corpus a entero `0..3`. `expect` seguirá siendo obligatorio durante esta migración y continuará alimentando MRR/recall@k. Cuando `relevance` esté presente, toda clave del corpus no declarada se interpreta como grado 0. Cuando esté ausente, `expect` conserva las métricas heredadas pero las métricas graduadas de esa consulta quedan como no disponibles: contenido no juzgado nunca se etiqueta automáticamente como irrelevante.

Las nuevas métricas usarán:

- ganancia `2^grado - 1` para `nDCG@5`;
- fracción de memorias juzgadas grado 3 presentes dentro de los tres primeros puestos para `essential-recall@3`;
- resultados grado 0 dividido entre resultados realmente servidos hasta cinco para `irrelevant-rate@5`;
- tokens estimados de resultados grado `1..3` divididos entre tokens estimados realmente servidos para densidad útil.

Una respuesta vacía no aporta denominador a densidad útil y no puede ocultar fallos: `essential-recall@3` y `nDCG@5` penalizan las memorias útiles omitidas. El informe conservará los detalles heredados y añadirá, por consulta, esenciales omitidas e irrelevantes servidas.

Alternativa descartada: sustituir `expect` de una vez. Rompería el dataset, las pruebas y los informes existentes sin aportar valor a la calibración.

### 5. Los negativos difíciles provienen de fixtures, no de producción

El dataset añadirá memorias temáticamente cercanas pero inútiles para una consulta concreta: estados históricos, otra herramienta con vocabulario similar, una decisión supersedida o un procedimiento del proyecto equivocado. También incluirá memorias grado 1 y 2 para impedir que el umbral optimice “cero ruido” devolviendo sólo una respuesta esencial.

No se copiará contenido real del usuario. Los ejemplos serán sintéticos y conservarán las etiquetas `semantic`, `exact`, `typo`, `identifier` y las cuatro direcciones español/inglés.

## Risks / Trade-offs

- [Un umbral vectorial elimina soporte multilingüe útil] → Proteger `es-es`, `es-en`, `en-en` y `en-es`, elegir el menor umbral que pase las guardas y dejar el default desactivado si ninguno pasa.
- [La similitud absoluta cambia al cambiar el modelo] → Registrar modelo/dataset/tunables en el informe y exigir recalibración antes de reutilizar el default con otro modelo.
- [FTS con OR todavía puede admitir una coincidencia superficial] → Incluir negativos lexicales difíciles; no añadir otro umbral salvo que el informe demuestre que esa pierna causa el ruido residual.
- [Una respuesta corta sorprende a clientes que asumían exactamente `limit` ítems] → Mantener el esquema y documentar que el límite siempre fue máximo; cubrir respuestas parciales y vacías en contratos MCP.
- [Optimizar sólo `irrelevant-rate` favorece devolver nada] → Usar simultáneamente `essential-recall@3`, `nDCG@5` y densidad útil como guardas obligatorias.

## Migration Plan

1. Extender el formato/evaluador y migrar gradualmente el dataset, conservando el informe heredado.
2. Ejecutar y guardar el baseline con admisión vectorial desactivada y el modelo vigente.
3. Implementar el filtro vectorial configurable y comparar candidatos mediante el mismo comando/dataset.
4. Activar como default sólo el valor que cumpla todas las guardas y documentar el experimento reproducible.
5. Desplegar sin migración de datos. Para rollback, configurar el umbral como desactivado; el flujo vuelve al pool vectorial vigente sin revertir esquema ni re-embebidos.

## Open Questions

- El valor numérico de `recall_vector_min_similarity` queda deliberadamente pendiente del experimento real-stack; la regla para seleccionarlo ya está cerrada.

## Experiment outcome (2026-08-29)

The bounded real-stack matrix in `experiment-record.md` (`embeddinggemma:300m`,
`scripts/eval_dataset.json`, throwaway PostgreSQL, production fusion weights)
found **no** `recall_vector_min_similarity` that reduces `irrelevant-rate@5`
without lowering `nDCG@5` or `essential-recall@3` globally or on a protected
language tag. The lowest candidates either left `irr@5` unchanged (0.25) or
dropped `en-en` nDCG 0.90→0.89 (0.35, 0.45); higher floors harm `es-es` or
collapse `es-en`/`en-es`. Residual noise is lexical (FTS/trigram hard
negatives), which a vector floor cannot cut without also dropping weak
cross-language vector hits.

**Default stays disabled (`None`).** The configurable predicate, evaluator, and
CLI override ship; a production number is blocked pending a design revision
(lexical admission, different guards, or a dataset that shows a guard-clean
win). Do not archive this change on the current decision.

## Follow-up threads (2026-08-30)

Closed against a fresh real-stack autopsy (`experiment-record.md`, same model
and dataset). Production default remains `None`. Still do not archive.

**A — residual noise is not a Vmin miss.** Of 90 top-5 grade-0 slots at
baseline, 72 are undeclared corpus (auto grade 0) and 18 are fixture hard
negatives. Those 18 are almost all `V+F` / `V+F+G`; FTS-only is 2 undeclared
rows. The vector floor cannot drop a hard negative FTS already admitted, which
is why 0.35 cuts unjudged kNN fill (`irr@5` 0.64→0.59) but does not improve
the explicit-zero rate (0.13→0.15).

**B — the en-en 0.01 nDCG dip is a real reorder, and `irr@5` is mostly
unjudged fill.** Tag 0.90→0.89 is one query (`how many approvals does a merge
need` 0.99→0.95) swapping `en-review-hotfix` (explicit 0) ahead of
`en-review-drafts` (grade 2), both `V+F`. Not four-query rounding. Shipped
`irr@5` treats undeclared keys as 0 (decision 4); that is ~0.51 of the 0.64.
Do not change the metric to make a Vmin pass. A future revision may *add*
an explicit-zero rate or require denser `relevance` maps.

**C — stop: do not tighten FTS or trigram in this change.** Decision 1 and
the FTS contract (`test_search_text_treats_every_term_as_optional`) keep
OR-any-lexeme. The autopsy did not prove FTS-only residual as the bulk of
`irr@5`. AND would re-break conversational queries; trigram-only is not in
the top 5. Follow-up, if any, is a new change (judgments / ranking), not a
predicate patch here.
