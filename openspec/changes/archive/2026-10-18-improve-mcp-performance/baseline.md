# Baseline — improve-mcp-performance phase 0

1.1 is production `tool_activity` (read-only, parent measurement).
1.2 and 1.3 are a disposable Docker `pgvector/pgvector:pg17` database, never production.

## 1.1 Tool latency

Window 2026-07-29..2026-10-18. 3642 tool_activity rows, 869 active memories, 2 users.

|tool|calls|p50ms|p95ms|maxms|%degraded|%failed|
|---|---:|---:|---:|---:|---:|---:|
|remember_batch|150|7466|26784|48590|0.0|6.0|
|update|294|3592|13406|30091|0.0|3.1|
|remember|553|3511|12061|29814|0.0|6.1|
|context|1575|5059|11933|30832|0.0|0.1|
|recall|977|740|7845|26710|0.0|2.9|
|merge_memories|11|2117|7274|8480|0.0|0.0|
|match_skills|2|5674|6923|7062|0.0|0.0|
|reconfirm|17|279|3838|4096|0.0|11.8|
|list_memories|17|32|174|200|0.0|0.0|
|get_memory|40|24|167|480|0.0|12.5|
|related_memories|3|51|90|94|0.0|0.0|
|forget|3|57|76|78|0.0|33.3|

Inter-arrival same user (3641 pairs): 7.8% within 5s, 25.5% within 30s, 32.4% within 60s, median gap 168s.

## 1.2 EXPLAIN (ANALYZE, BUFFERS)

Corpus: 870 active memories, one user, 768-dim vectors, `ANALYZE` after seed.
Statements are the ones the repository emitted during real service calls,
then re-explained in an RLS session with the preceding SET LOCAL / set_config
replayed. UUIDs and vectors redacted.
Execution time is one EXPLAIN ANALYZE sample; plan type is the stable signal.

|query|plan|node|execution time|
|---|---|---|---|
| vector | seq | ->  Seq Scan on memories | 11.456 ms |
| fts | seq | ->  Function Scan on unnest lexeme; ->  Function Scan on unnest lexeme_1; ->  Seq Scan on memories | 5.757 ms |
| trigram | seq | ->  Seq Scan on memories | 20.628 ms |
| context_top_global | seq | ->  Seq Scan on memories | 6.344 ms |
| dynamic | seq | ->  Seq Scan on memories | 1.045 ms |
| related_to | mixed | Index Scan memories_pkey seed; Seq Scan neighbour | 15.701 ms |
| context_top_project | index | ->  Bitmap Heap Scan on memories; ->  Bitmap Index Scan on ix_memories_user_project | 0.759 ms |

## 1.3 Statements and transactions per service call

Listener: SQLAlchemy before_cursor_execute (statements) and begin (transactions)
on the sync engine. Includes RLS set_config and SET LOCAL. Context rows below
are the warm path, after one cold call that materialized the profile.

|call|statements|transactions|
|---|---:|---:|
| context without focus | 10 | 2 |
| context with focus | 18 | 2 |
| recall | 11 | 2 |
| context immediately after recall | 10 | 2 |
| remember new | 12 | 2 |
| remember duplicate | 11 | 2 |

Cold context without focus (includes profile rebuild, not one of the six shapes): 21 statements, 5 transactions.

Harness ceilings (phase 0 only; task 8.1 replaces them): statements <= 80, transactions <= 20.

## 1.5 Pruning decision (design D0)

Reading of 1.1-1.3: at 869 active memories every hot query seq-scans in
1-21 ms; reads run 10-18 statements in 2 transactions. Production latency is
embedding-bound, not statement-bound (`recall` p50 740 ms with one embed;
`context` p50 5059 ms / p95 11933 ms; `remember` p50 3511 ms;
`remember_batch` p95 26784 ms; degraded 0.0% — slow successes, not failures).

Surviving batches, each citing its baseline number:

- 2.1 (`server_settings`): removes per-search `SET LOCAL` statements from the 10-18/call counts; `ef_search=100` (D1: margin over the 60-candidate cap; no plan change at 870 rows, `strict_order` already guarantees order).
- 2.2 (`related_to` two-step): 15.701 ms mixed plan today; makes the neighbour leg HNSW-indexable as the corpus grows past the seq-scan threshold. Neighbours served must not change.
- 3.1 (anchors only for served): pool `selectin` loads are inside the 11/18-statement recall/context-with-focus counts.
- 3.2 (dedup before embed): `remember` duplicate still pays the embed that makes new `remember` p50 3511 ms.
- 4.1-4.3 (read embedding budget): `recall` p95 7845 ms / max 26710 ms and `context` p50 5059 ms are the embed tail. Chosen values (D7 defaults): read timeout 3 s (median embed ≲740 ms per `recall` p50), negative window 5 s.
- 5.1-5.4 (deferred usage): recall's second transaction is `mark_recalled` (11 statements / 2 transactions); also the `agent-memory-retrieval` spec delta.
- 6.1 (auth one transaction): lookup + `touch` are two admin transactions today.
- 6.2 (identity TTL): inter-arrival gives an upper bound on cache hits — 7.8% of calls arrive within 5 s of the previous same-user call (marginal), 25.5% within 30 s. Per D8 the default rises to 30 s, declared as maximum revocation delay.
- 7.2 (proportional tops): `context` fetches `context_max_items_cap + 1` regardless of the requested budget (18-statement focus path).
- 7.3 (rebuild one transaction): cold `context` measured 21 statements / 5 transactions vs 10 / 2 warm.
- 8.1-8.3: statement ceilings and closure comparison, as designed.

Conditional, decided inside its batch by its own text:

- 2.3 (graph LATERAL order): apply only if a repeated EXPLAIN shows index use or clear improvement; at 870 rows the expected outcome is revert-with-note.

Closed as not justified at this scale (D0), checkboxes left open:

- 7.1 (partial index on `last_recalled_at`): dynamic selection is 1.045 ms seq on the comparable corpus; the planner would not choose the partial index at 870 rows. Revisit past ~10k active rows per user.
- 7.4 (`statistics()` to two queries): admin path, absent from `tool_activity` latency; nine ~ms queries on 870 rows.
- 7.5 (`history()` recursive CTE): `get_memory` p95 is 167 ms end-to-end; supersession chains are short, so the level loop is not a measured cost.

## 2.3 Graph LATERAL order — reverted

Repeated 1.2-style `EXPLAIN (ANALYZE, BUFFERS)` on a disposable
`pgvector/pgvector:pg17` database, 870 active memories, one user, 768-dim,
`ANALYZE` after seed. Scalable `graph_snapshot` (limit 1000, min_similarity
0.72, max_neighbours 4). One sample; plan type is the signal.

|order|plan|node|execution time|
|---|---|---|---|
| distance asc (`embedding <=>` , id) | seq | ->  Seq Scan on memories graph_left; ->  Seq Scan on memories graph_right | 23928.766 ms |
| score desc (previous: similarity DESC, id) | seq | ->  Seq Scan on memories graph_left; ->  Seq Scan on memories graph_right | 17909.528 ms |

Neither plan uses HNSW. Distance-ascending is slower on this sample, not an
improvement. The correlated outer embedding, `id = ANY(...)`, and
`COUNT(*) OVER ()` stay a per-node seq scan. Order left as score descending.

## Appendix — statement counts after batch 2

Same harness as 1.3, after removing per-search `SET LOCAL hnsw.iterative_scan`.
Cold context without focus unchanged: 21 statements, 5 transactions.

|call|phase-0 statements|after|transactions|
|---|---:|---:|---:|
| context without focus | 10 | 10 | 2 |
| context with focus | 18 | 17 | 2 |
| recall | 11 | 10 | 2 |
| context immediately after recall | 10 | 10 | 2 |
| remember new | 12 | 11 | 2 |
| remember duplicate | 11 | 11 | 2 |

Drops are the removed vector `SET LOCAL` (focus, recall, remember new).
The duplicate path did not emit that statement. `related_to` (not one of the
six shapes) is now 4 statements / 1 transaction; its neighbour EXPLAIN is a
seq scan on `related_neighbour` at 13.585 ms (phase-0 join was mixed, 15.701 ms).
Still seq at 870 rows. No production engine path bypasses the container, so
no `SET LOCAL` escape hatch was kept. Trigram `set_config` is unchanged.

## 2.4 Ranking evaluator

The parent ran `recallum-admin eval` (disposable pgvector DB + local Ollama
`nomic-embed-text`, `scripts/eval_dataset.json`, HEAD worktree vs working tree,
separate users). Reports are byte-identical except the corpus-seed line.
Before = after:

|tag|n|nDCG@5|ess@3|irr@5|
|---|---:|---:|---:|---:|
| semantic | 5 | 0.61 | 0.80 | 0.68 |
| exact | 3 | 1.00 | 1.00 | 0.67 |
| typo | 2 | 0.97 | 1.00 | 0.70 |
| identifier | 2 | 0.75 | 1.00 | 0.60 |
| es-es | 4 | 0.92 | 1.00 | 0.50 |
| es-en | 4 | 0.14 | 0.00 | 0.90 |
| en-en | 4 | 0.98 | 1.00 | 0.40 |
| en-es | 4 | 0.00 | 0.00 | 1.00 |
| overall | 28 | 0.63 | 0.68 | 0.69 |


## 8.3 Closure — before/after

Final counts are the permanent regression test
`tests/integration/test_call_budget.py` on the same disposable 870-memory
corpus as §1.3. The usage worker is stopped for the count windows; the
context-immediately-after-recall window flushes pending recall usage explicitly.

|call|phase-0 statements|phase-0 txns|final statements|final txns|
|---|---:|---:|---:|---:|
| context without focus | 10 | 2 | 6 | 1 |
| context with focus | 18 | 2 | 10 | 1 |
| recall | 11 | 2 | 7 | 2 |
| context immediately after recall | 10 | 2 | 8 | 2 |
| remember new | 12 | 2 | 13 | 3 |
| remember duplicate | 11 | 2 | 14 | 3 |
| cold context without focus | 21 | 5 | 15 | 2 |

EXPLAIN after, one sample, same corpus, `ANALYZE` after seed. Plan type is the signal.

|query|plan|node|execution time|
|---|---|---|---|
| vector | seq | ->  Seq Scan on memories | 9.972 ms |
| related_to | seq | ->  Seq Scan on memories related_neighbour | 15.644 ms |

`related_to` is the neighbour leg (`ORDER BY embedding <=> :seed`). The seed
read in that transaction is `WHERE memories.id = $1` and was not separately
explained. Still a seq scan at 870 rows; phase-0 join was mixed, 15.701 ms.

Production p50/p95: NOT re-measured. Production re-measurement requires a
deploy; production p50/p95 will only move after release. §1.1 is the before.

Evaluator: re-run after all batches; report byte-identical to the pre-change HEAD report (same disposable-DB + nomic-embed-text setup as §2.4).

Pruned, per §1.5: 7.1 (partial index on `last_recalled_at`), 7.4 (`statistics()`
to two queries), 7.5 (`history()` recursive CTE). 7.2 reverted — category-order
packing (`SessionContextBudget.assemble`) vs a scope-pool window; regression
test `test_context_serves_early_category_below_proportional_top_window`.

8.2 (parent run): `uv run pytest -q` = 1005 passed, 0 failed, 0 skipped, exit 0 (861s, includes Docker integration). `uv run mypy recallum` = clean, 85 files. `uv run ruff check .` initially failed on ONE pre-existing error untouched by this change (`plugins/recallum-memory/tests/test_plugin.py` E501), fixed as a disclosed drive-by in the closure clerical batch; gate then clean. Ranking evaluator after all batches (disposable DB + nomic-embed-text, as §2.4): report byte-identical to the pre-change HEAD report.

Context focus degradations are log-observable only (`embedding unavailable for context focus; using textual fallback`), unchanged from pre-change behavior. `UsageTelemetryMiddleware.on_call_tool` receives a FastMCP `ToolResult` after `convert_result` has already serialized the tool return into `structured_content`; the original `ContextResult` is not attached. `ContextResult` has no `mode` (output schemas are frozen). Telemetry has no contextvar or header channel for a degradation flag that is not in that schema (`diagnostics` correlation id and `current_identity` are unrelated). D7 telemetry parity applies where a mode exists: `recall` and `match_skills` (`structured["mode"] == "degraded_textual"`, including negative-window skips).

Superseded by the remaining-tasks closure below: the user un-pruned all four items.

## Remaining tasks closure (user un-pruned, 2026-10-18)

- 7.1 migration 0022 `ix_memories_user_last_recalled` `(user_id, last_recalled_at DESC)` partial, model mirror. EXPLAIN on seeded 870-row DB: with the app-shaped range+LIMIT and `enable_seqscan=off` (superuser) the new index is used (Index Scan + Incremental Sort), but under the app role with FORCE RLS at this scale the planner still chooses seq/bitmap plans (~4-row estimate from `current_setting`) — index is correct-by-construction, adoption expected as the corpus grows.
- 7.2 per-category `ROW_NUMBER` tops (bound: effective + min(effective, profile_context_max_items) + 1), invariant = identical output vs unbounded tops, ceilings unchanged (warm 6/1, focus 10/1).
- 7.4 statistics = 2 statements (GROUPING SETS + day series), output identical incl. empty corpus.
- 7.5 history = 1 recursive-CTE statement, identical order (`created_at`, `str(id)`), cycle cannot re-include the anchor (structurally impossible; arguably more correct).
- Verification: full suite 1012 passed, 0 failed, 0 skipped, exit 0 (923s); ruff clean; mypy clean 86 files; argus independent review pass/unmet none (3 minor findings: D9 wording fixed in this batch, EXPLAIN evidence recorded here, checkboxes below).
