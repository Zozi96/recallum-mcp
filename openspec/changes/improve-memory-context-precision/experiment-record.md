# Ranking experiment record — `recall_vector_min_similarity`

**Date:** 2026-08-29 — host `zozi` workstation
**Outcome:** no candidate in the bounded matrix reduced `irrelevant-rate@5` without
degrading a required guard. Production default stays **disabled** (`None`).
Do not archive this change; the admission requirement is unmet and needs a
design revision.

## Setup

Throwaway PostgreSQL 17 + pgvector (`docker run pgvector/pgvector:pg17` on
loopback, never the production Recallum database). Embeddings from the Swarm
Ollama service `recallum-ollama-wx1kcf` (`embeddinggemma:300m`, 768-d), reached
through a temporary localhost proxy. Dedicated user
`eval-precision@example.com`. Dataset: `scripts/eval_dataset.json` (59 corpus
rows, 28 queries tagged semantic/exact/typo/identifier/es-es/es-en/en-en/en-es),
seeded through ordinary `remember`.

```bash
export RECALLUM__DATABASE__URL=postgresql+asyncpg://recallum:app_test@127.0.0.1:<ephemeral>/recallum
export RECALLUM__OLLAMA__URL=http://127.0.0.1:11434
export RECALLUM__OLLAMA__MODEL=embeddinggemma:300m
uv run recallum-admin eval --email eval-precision@example.com \
  --dataset scripts/eval_dataset.json --k 10
# candidates add --vector-min-similarity <v>
```

Fusion tunables were the production defaults (importance 0.5, trigram 0.5,
usage 0.0, freshness 0.0). Usage therefore cannot explain ranking differences
across runs. `k=10` matches the production recall default.

## Reproducibility

After the corpus was present, two consecutive baseline runs (admission off)
produced **byte-identical** reports (`diff` empty between `baseline2` and
`baseline3`). A first seed run differed only in `corpus: 59 seeded, 0 already
present` versus `0 seeded, 59 already present`; every MRR, recall@k, and
graded line matched.

## Baseline (admission disabled)

| tag | n | MRR | R@10 | nDCG@5 | ess@3 | irr@5 | useful-tok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| semantic | 5 | 0.70 | 1.00 | 0.69 | 0.80 | 0.68 | 0.20 |
| exact | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 0.16 |
| typo | 2 | 1.00 | 1.00 | 0.97 | 1.00 | 0.70 | 0.14 |
| identifier | 2 | 0.75 | 1.00 | 0.83 | 1.00 | 0.60 | 0.22 |
| es-es | 4 | 1.00 | 1.00 | 0.88 | 1.00 | 0.55 | 0.25 |
| es-en | 4 | 0.62 | 1.00 | 0.61 | 0.50 | 0.70 | 0.20 |
| en-en | 4 | 0.88 | 1.00 | 0.90 | 1.00 | 0.40 | 0.31 |
| en-es | 4 | 0.34 | 0.75 | 0.31 | 0.25 | 0.85 | 0.12 |
| **overall** | **28** | **0.76** | **0.96** | **0.74** | **0.79** | **0.64** | **0.20** |

Protected multilingual tags for the default rule: `es-es`, `es-en`, `en-en`,
`en-es`.

## Candidate matrix

Same database state, model, dataset, and fusion weights. Only
`recall_vector_min_similarity` changes.

| Vmin | overall nDCG@5 | ess@3 | irr@5 | useful-tok | es-es nDCG/ess | es-en nDCG/ess | en-en nDCG/ess | en-es nDCG/ess | irr reduced? | guards |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| off | 0.74 | 0.79 | 0.64 | 0.20 | 0.88 / 1.00 | 0.61 / 0.50 | 0.90 / 1.00 | 0.31 / 0.25 | — | baseline |
| 0.25 | 0.76 | 0.82 | 0.64 | 0.21 | 0.91 / 1.00 | 0.61 / 0.50 | 0.90 / 1.00 | 0.35 / 0.50 | no | fail: irr@5 unchanged |
| 0.35 | 0.80 | 0.89 | 0.59 | 0.28 | 0.91 / 1.00 | 0.66 / 0.75 | **0.89** / 1.00 | 0.68 / 0.75 | yes | fail: en-en nDCG 0.90→0.89 |
| 0.45 | 0.80 | 0.93 | 0.47 | 0.45 | 0.88 / 1.00 | 0.77 / 1.00 | **0.89** / 1.00 | 0.64 / 0.75 | yes | fail: en-en nDCG 0.90→0.89 |
| 0.55 | 0.75 | 0.89 | 0.46 | 0.45 | **0.83** / 1.00 | 0.80 / 1.00 | 0.97 / 1.00 | 0.57 / 0.75 | yes | fail: es-es nDCG 0.88→0.83 |
| 0.65 | **0.56** | **0.68** | 0.51 | 0.39 | 0.91 / 1.00 | **0.37** / 0.50 | 0.89 / 1.00 | **0.19** / 0.25 | yes | fail: overall + mixed-language nDCG/ess |
| 0.75 | **0.50** | **0.57** | 0.52 | 0.37 | **0.73** / **0.75** | **0.19** / **0.25** | 0.89 / 1.00 | **0.00** / **0.00** | yes | fail: overall + multilingual collapse |

Selection rule (design decision 3): lowest Vmin that (1) does not reduce
`essential-recall@3` or `nDCG@5` globally or on the four language tags,
(2) reduces `irrelevant-rate@5`, and (3) does not reduce useful-token density.
No intuition override.

## Decision

**Keep `MemoryLimits.recall_vector_min_similarity = None`.** Unit test
`test_recall_vector_min_similarity_defaults_disabled_and_is_capped` pins that
default.

Residual `irr@5` ≈ 0.64 with the vector floor off is mostly lexical: FTS/trigram
still admit hard negatives (near-synonym tools, superseded procedures, same
project wrong fact). Raising Vmin enough to cut that tail also clips weak but
required cross-language vector hits (`en-es` / `es-en`) or a 0.01 `en-en` nDCG
dip at 0.35–0.45. A production number would violate the written guards.

Rollback remains: leave the knob unset (already the default).

## Spec scenario coverage

| Spec scenario | Evidence |
| --- | --- |
| Limit not filled with weak vector neighbours | `tests/unit/test_service.py::test_recall_vector_min_similarity_drops_weak_neighbors_below_limit` |
| No useful memory → empty recall | `test_recall_vector_min_similarity_returns_empty_when_nothing_qualifies` |
| Support context conserved when admitted | `test_recall_vector_min_similarity_keeps_admitted_support` |
| `context(focus=...)` uses the same floor; profile intact | `tests/unit/test_memory_profile.py` (floor 0.99) |
| Textual degradation, `mode=degraded_textual` | `tests/unit/test_service.py`, `tests/integration/test_db.py` |
| Graded report / tunables compare / short-list scoring / hard negative / inherited dataset | `tests/unit/test_evaluation.py`, `tests/unit/test_cli.py` |
| Exact / typo / identifier / no-match / language 2×2 | this record + shipped dataset tags |
| Compare admission vs fusion on protected tags | this matrix |

This report is the ranking evaluator only (MRR, recall@k, graded metrics). It
does not mix workflow/checkpoint evaluator numbers.

## Follow-up threads (2026-08-30)

Same throwaway stack recipe as above (fresh `pgvector/pgvector:pg17` on
loopback, Ollama `embeddinggemma:300m` via localhost proxy, user
`eval-precision@example.com`, `scripts/eval_dataset.json`, production fusion
weights, `k=10`). After ordinary `remember` seeding, each query was served
through `recall` and the same query/embedding was run through
`search_candidates` so every returned row could be tagged with the admitting
legs: `V` vector, `F` FTS, `G` trigram. Raw dump:
`/tmp/recallum-eval-precision/autopsy.json` (ephemeral). Counts below are the
durable copy.

### A — per-leg autopsy of served irrelevants

28 queries × 5 = 140 top-5 slots. Baseline (Vmin unset) put **90** grade-0
rows in those slots (`irr@5` 0.64).

Top-5 grade-0 by admitting legs:

| legs | all grade-0 | explicit 0 (hard neg) | undeclared (auto-0) |
| --- | ---: | ---: | ---: |
| V only | 36 | 2 | 34 |
| V+F | 43 | 9 | 34 |
| V+F+G | 7 | 7 | 0 |
| V+G | 2 | 0 | 2 |
| F only | 2 | 0 | 2 |
| **total** | **90** | **18** | **72** |

Designed hard negatives in the top 5 are almost all multi-leg (`V+F` or
`V+F+G`, 16/18). A vector cosine floor cannot drop them: FTS already admitted
them. FTS-only noise in the top 5 is 2 undeclared rows, not the designed
negatives. Trigram-only is absent from the top 5.

At Vmin 0.35, `irr@5` falls 0.64 → 0.59 because undeclared vector-only fill
shrinks (unjudged rate 0.51 → 0.44). Explicit-zero rate in the top 5 **rises**
slightly (0.13 → 0.15): hard negatives stay, and RRF promotes some of them
when weaker undeclared neighbours leave. FTS-only undeclared in the top 5
rises from 2 to 10 once the vector pool is gated — lexical OR residual becomes
visible *after* Vmin, it is not the bulk of baseline `irr@5`.

### B — en-en 0.90→0.89 and undeclared-as-0 `irr@5`

The tag mean 0.90 → 0.89 is **not rounding noise**. Live nDCG@5 on the four
`en-en` queries:

| query | off | Vmin 0.35 | Δ |
| --- | ---: | ---: | ---: |
| when does the staging data get wiped | 0.95 | 0.95 | 0 |
| who is on call this week | 0.67 | 0.68 | +0.01 |
| how many approvals does a merge need | 0.99 | 0.95 | **−0.04** |
| how long are audit logs kept | 0.99 | 1.00 | +0.01 |
| **tag mean** | **0.90** | **0.89** | **−0.01** |

The only drop is `how many approvals does a merge need`: `en-review-hotfix`
(explicit 0, `V+F`) swapped with `en-review-drafts` (grade 2, `V+F`) at ranks
2–3. Same two legs; Vmin did not remove the hard negative, it reordered two
FTS-admitted rows. Other nDCG drops at 0.35: `for_user transaction` 1.00→0.83,
`which package manager should I use` 0.95→0.90.

`irr@5` with undeclared keys treated as 0 (design decision 4) vs alternatives
on the same rankings:

| definition | off | Vmin 0.35 |
| --- | ---: | ---: |
| undeclared = 0 (shipped) | 0.64 | 0.59 |
| numerator = explicit 0 only | 0.13 | 0.15 |
| judged served items only | 0.24 | 0.26 |
| unjudged fraction of top 5 | 0.51 | 0.44 |

Four-fifths of shipped `irr@5` is auto-labelled unjudged corpus, not the
fixture hard negatives. Vmin 0.35 improves the shipped metric by cutting that
unjudged fill, while the designed-negative rate does not improve. Do **not**
retcon the failed matrix by changing `irr@5` after the fact; a later design
revision may add an explicit-zero rate or denser `relevance` maps, but the
written guards still fail on the metric as specified.

### C — FTS / trigram admission: stop, do not implement

No FTS or trigram predicate change in this change.

- Design decision 1: FTS and trigram keep their current predicates.
- Design risk: do not add another lexical threshold unless the report proves
  that leg is the residual. It is not: baseline top-5 explicit zeros are
  co-admitted by vector+FTS; F-only is 2/90 grade-0 slots.
- AND-ing query terms is the previously broken production behaviour. Contract
  `tests/contract/memory_repository.py::test_search_text_treats_every_term_as_optional`
  pins OR-any-lexeme (`_or_tsquery`) against `websearch_to_tsquery`. Tightening
  FTS here would fail that contract and harm conversational / mixed-language
  queries. Trigram remains the typo/identifier net; G-only is not in the top 5.

A later change could look at FTS *ranking* (coverage already exists via
`ts_rank_cd`) or denser judgments. It must not silently AND the tsquery.
