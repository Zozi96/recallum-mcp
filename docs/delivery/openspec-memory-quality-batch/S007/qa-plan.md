# QA plan — S007: Scalable bounded graph edges behind an opt-in flag, preserving honest truncation

## Risks and cheapest detection layer

1. **Critical — the routing matrix silently changes the default.** Flag off + node count under threshold must keep the pairwise path byte-for-byte; "exceeding the threshold" means strict `>`; flag on routes regardless of count. An off-by-one (`>=`) or a flag defaulting to on flips production behavior. Unit — the routing decision is a pure function over config, provable with a fake repo and a routing marker; no SQL needed.
2. **Critical — edge-set and signal parity between the two paths.** The bounded per-node query must return exactly the pairwise edge set and identical `edge_total`/`edges_truncated` when caps do not bite. Integration — parity only holds if both real SQL implementations are compared; a fake that re-implements either path would prove the fake, not the code.
3. **High — signals computed from the wrong counts.** `edge_total` is the pre-cap qualifying undirected-pair count (pair counted once, not per endpoint), and `edges_truncated` is true iff ≥1 pair was dropped because an endpoint hit the cap. Wiring either to `len(returned edges)` reintroduces the silent-drop failure this story exists to fix. Unit — signal derivation is pure service logic over a `GraphSnapshot` carrying the pre-cap count.
4. **High — regression of the unchanged pairwise default.** Existing `test_service.py` graph tests, `memory_repository.py` contract tests, and the `graph_max_nodes` cap test are the regression net. Unit + integration — the existing suites must stay green unmodified; that is the default-path contract.
5. **Medium — the new SQL loses the honesty filters.** The bounded query must keep `embedding_model` equality + non-null and `min_similarity`; a node with all relations below threshold must get no invented edge; cross-model pairs must stay out of both edge sets and `edge_total`. Integration — these are SQL `WHERE` clauses; only a real pgvector run shows them.
6. **Medium — `related_to` alignment drifts or regresses.** It is already per-node bounded; alignment must not change results under either activation state. Integration — real-DB semantics check under both routing states.
7. **Medium — stale OpenAPI snapshot.** New response fields must serialize; `test_versioned_openapi_matches_web_app_only` (`tests/unit/test_self_service_api.py:468`) enforces regeneration. Unit — existing test; the check is that `openapi/web-v1.json` shows both fields.

## Checks, fixtures, and layers

- **Unit — routing matrix:** parameterized over flag {off, on} × count {threshold−1, threshold, threshold+1}: off+below → pairwise; off+at → pairwise (strict `>`); off+above → scalable; on+any → scalable. Assert default flag is `False` and default threshold sits above `graph_max_nodes` default (effective default = pairwise). Uses `FakeMemoryRepository`, `ScriptedEmbeddingClient` vectors as today.
- **Unit — signal derivation:** given a fake `GraphSnapshot` with pre-cap qualifying count and pairs: dense fixture (hub node with `graph_max_neighbours+1` qualifying neighbours) → returned edges are the strongest k, `edges_truncated is True`, `edge_total` == pre-cap count (> len(edges)); sparse fixture (all nodes within cap) → `edges_truncated is False`, `edge_total == len(edges)`; empty/one-node snapshot → `edge_total == 0`, `edges_truncated is False`.
- **Unit — no invented neighbours:** node whose qualifying relations are all below `graph_min_similarity` (or single-model-isolated) contributes zero edges and zero to `edge_total`.
- **Unit — determinism/idempotency:** two `memory_graph` calls over an identical snapshot return identical edge ordering (score desc, id tiebreak) and identical signals.
- **Unit — `MemoryLimits` validation:** new flag is bool defaulting false; new threshold bound (`gt=0`); existing `graph_max_neighbours`/`graph_min_similarity` bounds unchanged.
- **Integration — pairwise/scalable parity (real pgvector):** fixture of 6+ memories with crafted distinct-similarity embeddings, one model, cap high enough that no per-node cap bites: scalable edge set == pairwise edge set exactly, `edge_total`/`edges_truncated` identical. Second parity fixture includes one equal-similarity tie pair to pin cross-path tie ordering.
- **Integration — dense truncation parity:** hub with k+1 qualifying neighbours: both paths return the same k strongest edges, `edges_truncated is True`, `edge_total` identical.
- **Integration — activation:** same fixture routed via flag-on (under threshold) vs threshold-only (flag off) vs pairwise; all three produce identical results on a no-cap fixture, and threshold-only must equal pairwise exactly on the dense fixture.
- **Integration — honesty filters in SQL:** cross-model fixture (`embedding_model="other-model"`) and a below-threshold-only node: excluded from both paths' edge sets and from `edge_total`; `graph_snapshot`/`related_to` cross-bucket-not-users-and-models contract tests stay green.
- **Integration — `related_to`:** under both activation states, per-node bounded result, `min_similarity` honored, stable ordering, existing contract tests green.
- **Integration — determinism contract test extended:** repeated `graph_snapshot` returns identical pairs and identical new-signal values (extend `test_graph_snapshot_is_deterministically_bounded`).
- **Unit/snapshot — response schema:** `MemoryGraphResponse` carries `edge_total: int`, `edges_truncated: bool`; `openapi/web-v1.json` regenerated so `test_versioned_openapi_matches_web_app_only` passes and `/me/memory-graph` schema shows both fields.
- **Docs inspection — activation runbook:** `docs/operations.md`/runbook states flag and/or `count > threshold` activate the scalable path and that default deployments keep pairwise. No behavior asserted, just presence and accuracy.

## Operational done criteria

Stage 8 returns pass only when: the fast lane `uv run pytest tests/unit -m "not integration and not vertical and not traefik"` is green (new routing/signal/validation tests collected and passing; existing graph tests unchanged); the integration lane against real PostgreSQL+pgvector is green (parity, dense truncation, activation, honesty-filter, `related_to`, determinism contract tests); `test_versioned_openapi_matches_web_app_only` passes with `web-v1.json` containing `edge_total`/`edges_truncated`; and the operations/runbook activation note is present and reviewed. Any skipped, retried, or environment-blocked check is fail/block, not pass.

## Blocking dependencies

Real PostgreSQL+pgvector for the integration lane (`RECALLUM_TEST_DATABASE_URL` or Docker); locked `uv` dev toolchain; no external model service — fixtures use crafted/scripted embeddings via existing fakes, and the graph uses stored embeddings only, so Ollama/network/credentials are not required. OpenAPI export script (`scripts/export_web_openapi.py`) must be runnable to regenerate the snapshot.

## Deliberate coverage gaps

- **No performance/index benchmarks:** kNN query cost is measured, not gated — thresholds would be environment-flaky. Only a structural bound (per-node query keeps its `LIMIT`; no new index required) is checked by inspection.
- **No production-volume (1000+ node) runs:** parity is proven on small fixtures only, per story; scale behavior is runbook guidance, not a gate.
- **No concurrent-write races:** graph reads under RLS are unchanged; no new write path.
- **No `graph_max_nodes` re-testing:** the ceiling is out of scope; the existing cap test is the regression net.
- **No UI/full-graph tool coverage:** out of scope by story.
- **No `total`/`truncated` meaning changes:** explicitly excluded by story; asserted unchanged by the unmodified existing tests.
