## Why

`improve-memory-context-precision` shipped the vector floor, the graded evaluator, and a real-stack matrix, but no `recall_vector_min_similarity` passed the written guards. The 2026-08-30 autopsy showed why: shipped `irr@5` is ~80% unjudged corpus (undeclared keys treated as 0) and the fixture hard negatives are co-admitted by FTS+vector, so a cosine floor cannot drop them. A production default is still blocked; this change exists to make a guard-clean calibration possible without retconning `irr@5` or AND-ing FTS.

## What Changes

- Densify `scripts/eval_dataset.json` `relevance` maps so every key a baseline `recall` actually serves in the top-k, and every designed hard negative on the same theme, is judged explicitly. Undeclared keys remain grade 0.
- Report `explicit-zero-rate@5` and `unjudged-rate@5` alongside shipped `irr@5`. Do not change the definition of `irr@5` (undeclared = 0).
- Re-run the real-stack Vmin matrix with the same production guards (`nDCG@5`, `essential-recall@3`, `irr@5`, useful-token density, protected language tags). Enable the lowest passing threshold, or keep `None` and document the new block.
- Leave FTS OR-any-lexeme, trigram predicates, RRF, MCP schema, and fusion weight defaults unchanged.
- After a passing default (or a documented second block), archive `improve-memory-context-precision` together with this change.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `agent-memory-retrieval`: exigir juicios densos en el dataset de ranking y que el informe separe ceros explícitos y no juzgados sin redefinir `irrelevant-rate@5`; la admisión vectorial de producción sigue las mismas guardas, ahora sobre ese dataset.

## Impact

- Afecta el evaluador de ranking, el dataset versionado, el informe CLI y, si la matriz pasa, el default de `MemoryLimits.recall_vector_min_similarity`.
- No cambia el esquema MCP, las predicados FTS/trigram, RLS, ni las dependencias.
- Compatible para clientes: el comportamiento de `recall` sólo cambia si un umbral pasa las guardas y se activa como default.
