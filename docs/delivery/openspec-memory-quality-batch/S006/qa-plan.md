# QA plan — S006: Usage vote in recall ranking: reproducible evaluation and measured default stays at 0.0

## Risks and cheapest detection layer

1. **Critical — the cap breaks or the vote is smuggled.** A usage voter that adds an absolute `recall_count` score, uses raw list position instead of competition ranking, or carries a weight > 1.0 lets usage displace a clearly better semantic/exact match. Cheapest at unit: `_reciprocal_rank_fusion` is a pure function over scored candidate pools; scripted embedder + injected `recall_count` proves the cap deterministically. Integration cannot pin "clearly better" without embedding noise.
2. **High — the default silently leaves 0.0 and regresses production ranking.** Any change to `MemoryLimits.recall_usage_weight` default, or a weight-0 path that reorders, is a silent production behavior change. Cheapest at unit: default assertion plus fusion equality at weight 0.
3. **High — the experiment is vacuous or non-comparable.** `run_eval` seeds into a user whose memories all start at `recall_count=0` and itself mutates counts mid-run; at any positive weight, equal counts mean no reorder, so the candidate run can equal the baseline for the wrong reason. Cheapest: unit reproducibility double-run plus review of the experiment record, which must state what the candidate run actually exercised.
4. **High — the usage-weight override is missing or mis-threaded.** Without `--usage-weight`, baseline and candidate cannot be compared on identical config. Cheapest at unit: parser + override plumbing captured via monkeypatched `run_eval`.
5. **Medium — the ranking report blends workflow-evaluator metrics or loses tag annotation.** Cheapest at unit: `render_report` output assertions.
6. **Medium — per-user isolation regresses** (usage reads cross-user counts or deleted rows). Cheapest at unit: two-user fake-repo test; RLS already enforced by repository layer.
7. **Low — reproducibility drift** (time, unordered sets, mid-run count mutation). Cheapest at unit: two `run_eval` runs on the same dataset/config must render identical reports.

## Checks, fixtures, and layers

- **Unit — fusion cap and competition ranking** (`tests/unit/test_service.py` or `test_agent_synergy.py`, fake repo + `ScriptedEmbeddingClient`, `recall_trigram_weight=0.0` to pin the fixture): (a) weight 0.0 → ordering identical to the relevance/importance baseline, usage voter contributes nothing; (b) weight > 0 → a memory with higher `recall_count` overtakes a candidate relevance scored close; (c) cap: at weight 1.0 (the max), a usage-#1 memory cannot displace a candidate ranked #1 in both vector and text legs; (d) competition ranking: equal `recall_count` → equal contribution, recency does not sneak through the tie-break; (e) all counts equal at weight > 0 → no reordering; (f) weight 0.5 candidate case reorders the engineered tie (extends the existing `test_recall_usage_weight_breaks_retrieval_ties`).
- **Unit — limits boundaries:** `MemoryLimits().recall_usage_weight == 0.0`; `MemoryLimits(recall_usage_weight=-0.1)` and `1.1` raise; `1.0` is accepted (cap).
- **Unit — dataset and eval plumbing** (`tests/unit/test_evaluation.py`, real `scripts/eval_dataset.json` as fixture for the pairing test): existing shape-error, metric-edge, tag-aggregation, idempotent-reseed, and misses-tagged-by-`[tag]` tests stay green; `render_report` contains MRR/recall@k per-tag table, `tunables:` line, tagged misses, and **no workflow-evaluator metric names**.
- **Unit — reproducibility / dry run:** two `run_eval(service, USER, dataset, k=...)` calls on the same fake service → byte-identical `render_report`; repeatable, offline, no clock/random/network.
- **Unit — CLI override** (`tests/unit/test_cli.py`): `--usage-weight` parses as `float` (default `None`); eval with an unknown email exits 1; with `--usage-weight 0.3` and `monkeypatch` on `recallum.cli.run_eval`, the captured `MemoryService` has `limits.recall_usage_weight == 0.3` and the recorded `report.tunables` contains `recall_usage_weight`.
- **Unit — isolation:** two users with identical corpus but different `recall_count` on their rows; `recall` for user B at weight > 0 returns only B's active memories and breaks B's ties from B's own counts only.
- **Integration — real stack (only if available):** `recallum-admin eval --email <dedicated eval user> --dataset scripts/eval_dataset.json --usage-weight 0.0` and `--usage-weight <candidate>` both print a report without error; reports differ only if counts justify it.
- **Repo inspection — evidence review:** the experiment record shows baseline (0.0) and ≥ 1 candidate (> 0) MRR/recall@k/misses side by side and states the decision to keep the production default at 0.0 with no config change; `recallum/memory/limits.py` still defaults `recall_usage_weight` to 0.0; tunables docs document `eval` and the override.

## Operational done criteria

Stage 8 returns **pass** only when all of the following hold; anything skipped, retried, or environment-blocked is `fail`/`blocked`, not pass:

1. `uv run pytest tests/unit -m "not integration and not vertical and not traefik"` is green, and the new fusion, limits, eval-plumbing, CLI-override, isolation, and reproducibility tests are collected by it (no `integration`/`vertical`/`traefik` marker on them).
2. The dry reproducibility run above produces byte-identical reports on two executions.
3. The cap, competition-ranking, weight-0-no-reorder, and limits-boundary unit checks all assert their exact invariants above.
4. The CLI override check proves `--usage-weight` reaches the eval service limits and the report's `tunables`.
5. The repo-inspection evidence review passes: experiment record complete (both runs + decision), `limits.py` default still 0.0, docs updated.
6. If PostgreSQL + Ollama are available, the real-stack baseline/candidate runs execute and print reports; if not, that pair is recorded as `blocked` in `qa-report.md` — it is a separate check from the dry gate, which must still pass.

## Blocking dependencies

`uv` / Python 3.14 dev toolchain; `scripts/eval_dataset.json` present, valid, and versioned. The real-stack re-run needs PostgreSQL (via `RECALLUM_TEST_DATABASE_URL` or Docker) and a local Ollama `embeddinggemma 300m` — absent either, only the real-stack pair is blocked; the dry gate and evidence review run offline.

## Deliberate coverage gaps

- No real-Ollama re-run of the experiment when the environment lacks PG/Ollama: the implementation's experiment record is accepted as delivery evidence; the dry reproducibility gate carries reproducibility.
- No audit of dataset representativeness beyond the shipped language 2×2 pairing invariant; no new synthetic-fixture content is authored by this plan.
- No concurrency/parallel-recall or large-pool performance tests of fusion; per-user RLS isolation is delegated to the existing repository-contract/integration suite.
- No candidate weights beyond the single value the experiment record chooses.
- No interaction with the workflow/checkpoint evaluator (explicitly out of scope).
- No judgment on whether keeping 0.0 is the *right* tuning decision — only that the record states it and no config changed.
