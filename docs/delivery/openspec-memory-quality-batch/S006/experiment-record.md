# S006 ranking experiment record — usage vote in recall fusion

**Date:** 2026-08-16 — host `zozi` workstation
**Outcome:** baseline (usage weight 0.0) and two candidates (> 0) run side by side on the
identical versioned dataset and configuration. Every number below is a real-stack run
(PostgreSQL 17 + pgvector, Ollama `embeddinggemma:300m`), not a fixture.

## Setup

Dedicated eval user `eval@example.com` in a throwaway local database (never the production
store). Dataset: `scripts/eval_dataset.json` (versioned, 18 corpus rows, 28 queries tagged
semantic/exact/typo/identifier/es-es/es-en/en-en/en-es), seeded through the ordinary
`remember` path. Invocation:

```bash
uv run recallum-admin eval --email eval@example.com --dataset scripts/eval_dataset.json --k 10
# baseline; and with --usage-weight 0.3 / --usage-weight 0.5 for the candidates
```

Each run replays the 28 queries through `MemoryService.recall` (full RRF fusion, importance
weight 0.5, trigram weight 0.5). `recall_count` is recorded on every served row, so a run
mutates usage exactly as production does.

## Runs

| run | usage weight | overall MRR | recall@10 | misses | exercised usage |
| --- | --- | --- | --- | --- | --- |
| baseline | 0.0 | **0.82** | 1.00 | none | all counts 0 |
| candidate A | 0.3 | **0.79** | 1.00 | none | counts 2–28, accumulated by baseline serving |
| candidate B | 0.5 | **0.78** | 1.00 | none | counts 2–30, accumulated by prior runs |

The candidate runs are not vacuous: after the baseline's natural recalls, the eval user's 18
memories carried recall counts from 2 to 28 (distinct per row), so the usage vote had real
differentials to act on. A candidate run from an all-equal-count state produced 0.80,
confirming the vote is inert when counts are equal and moves the report only when usage
differs.

## Per-tag MRR

| tag | baseline (0.0) | candidate A (0.3) | candidate B (0.5) |
| --- | --- | --- | --- |
| semantic | 0.90 | 0.90 | 0.90 |
| exact | 1.00 | 1.00 | 1.00 |
| typo | 1.00 | 1.00 | 1.00 |
| identifier | 1.00 | 1.00 | 1.00 |
| es-es | 1.00 | 1.00 | 1.00 |
| es-en | 0.49 | 0.31 | 0.26 |
| en-en | 1.00 | 1.00 | 1.00 |
| en-es | 0.38 | 0.36 | 0.36 |
| **overall** | **0.82** | **0.79** | **0.78** |

The degradation concentrates in `es-en` (Spanish memory queried in English), where the
vector leg is weakest: the usage vote lifts frequently-served English rows ahead of the
expected Spanish memory — the rich-get-richer failure mode this knob exists to gate. The
clearly-correct tags (exact, identifier, typo, en-en, es-es) are untouched at every weight,
matching the cap's guarantee.

## Reproducibility

- Unit/dry gate: two `run_eval` executions on the same dataset and configuration produce
  byte-identical reports (`tests/unit/test_evaluation.py::test_run_eval_is_dry_and_reproducible`).
- Real stack: resetting the eval user's counts to an identical state and running the same
  command twice produced byte-identical reports (`diff` empty) at weight 0.0 and weight 0.3.

## Decision

**Keep the production default `recall_usage_weight = 0.0`. No configuration change ships.**
The experiment shows a monotonic MRR loss as the weight grows (0.82 → 0.79 → 0.78 on the
synthetic dataset), with the damage concentrated in the mixed-language tags. The knob, the
override, and the measurement contract ship; a non-zero default would need a dataset that
shows a win, evaluated the same way, in a future change.

The report above is the ranking evaluator's own output (MRR, recall@k, tagged misses only);
it never blends workflow/checkpoint evaluator metrics (`scripts/eval_agent_workflow.py` is a
separate command and measurement surface).

## Stage-8 reconfirmation (2026-08-17)

Re-ran on a throwaway `pgvector/pgvector:pg17` (loopback `:55432`, user `eval@example.com`)
plus the host Swarm Ollama (`embeddinggemma:300m`) proxied at `127.0.0.1:11434`. Never the
production Recallum database. Same command as above.

| run | usage weight | overall MRR | recall@10 | es-en MRR | en-es MRR |
| --- | --- | --- | --- | --- | --- |
| baseline | 0.0 | **0.82** | 1.00 | 0.49 | 0.38 |
| candidate | 0.3 | **0.79** | 1.00 | 0.31 | 0.36 |

Numbers match the original table tag-for-tag. Default stays **0.0**.
