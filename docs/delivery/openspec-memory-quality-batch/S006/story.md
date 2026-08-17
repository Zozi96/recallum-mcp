# S006 — Usage vote in recall ranking: reproducible evaluation and measured default stays at 0.0

## Actor
An operator/tuner running `recallum-admin eval` against the golden dataset; recall fusion consumers.

## Objective and motivation
`recall_count` and service-time usage are already recorded, and `recall_usage_weight` already exists at 0.0, but enabling it would be a blind rich-get-richer loop without a measurable ranking contract. This story makes ranking evaluation reproducible, verifies the usage vote respects its cap and isolation, runs the baseline-vs-candidate experiment, and keeps the production default at 0.0.

## In scope
- Versioned ranking dataset with tags and expected keys (the existing `scripts/eval_dataset.json` is the artifact; synthetic/fixture content only, no production data).
- Documented ranking evaluation command producing MRR, recall@k, and misses per query tag, separate from the workflow/checkpoint evaluator; expose a usage-weight override so baseline and candidate runs are comparable on the same dataset.
- Verify/complete the usage vote in `recall` fusion: it must respect `recall_usage_weight`, use the same competition-ranking mechanism as importance, and be capped so it cannot outweigh a primary retrieval signal.
- Confirm the default stays 0.0 and per-user isolation holds in tests.
- Run the experiment: baseline (weight 0) and at least one candidate weight > 0 against the dataset; record the result and the decision not to change (or to defer) the production default.
- Unit tests of the fusion with weight 0 vs > 0, and a dry, reproducible ranking eval run.

## Out of scope
- Changing the production default to a non-zero weight.
- Changing the workflow/checkpoint evaluator or adherence cycle.
- Graph edges, corpus auto-hygiene, new schemas, or new telemetry.

## Mapped OpenSpec tasks
Source change: `tune-recall-usage-ranking` — tasks 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2.

## Dependencies
No story dependency. Builds on the existing usage voter wiring in `MemoryService.recall`, `recallum/evaluation.py`, and the `eval` subcommand in `recallum/cli.py`.

## Acceptance criteria
- The documented eval command run against `scripts/eval_dataset.json` produces a report with MRR, recall@k, and a misses list annotated by query tag, with no workflow-evaluator metrics blended in.
- The eval command accepts a usage-weight override, so the baseline and a candidate weight can be compared on the identical dataset and configuration.
- Fusion unit tests with `recall_usage_weight = 0.0` assert the `recall` ordering equals the current relevance/importance ordering (usage causes no reordering).
- Fusion unit tests with a weight > 0 assert that higher `recall_count` can reorder candidates that relevance already scored close together but cannot displace a clearly better semantic or exact-text match (the cap holds), and that only the authenticated user's active memories participate.
- The experiment record shows baseline (0.0) and at least one candidate (> 0) MRR/recall@k/misses side by side, and states the decision to keep the production default at 0.0 with no config change.
- The ranking eval suite runs dry and reproducibly: the same dataset and configuration produce the same report on repeated runs.

## Assumptions
- The production default remains 0.0 regardless of the experiment outcome; this change never ships a default > 0 (per the change design).
- `scripts/eval_dataset.json` is the versioned ranking dataset; extending it is allowed only with non-production synthetic/fixture content.
- The usage signal is the already-persisted `recall_count` and service-time usage signals; no new schema or telemetry is added.

## Open questions
- Which candidate weight(s) should the experiment evaluate (e.g., 0.1, 0.3)? Any small value under the cap satisfies the spec; a team preference would fix the record.

## Affected surface
`recallum/cli.py` (eval override), `recallum/evaluation.py` (misses/tag reporting if incomplete), `recallum/memory/service.py` (fusion verification), `recallum/memory/limits.py` (default unchanged), `tests/unit/test_evaluation.py`, `tests/unit/test_service.py`, tunables docs, experiment record.

## Risks
Rich-get-richer → default 0.0, capped small weight, evaluate misses not just MRR. Synthetic dataset not representative → keep tags and extend only with operator-provided PII-free fixtures.

## Validation expectations
Fusion unit tests at weight 0 and > 0; reproducible dry eval run; experiment report reviewed as delivery evidence.

## Boundary crossings
Agent-memory-retrieval. No schema, auth, or identity changes; evidence-only artifacts.
