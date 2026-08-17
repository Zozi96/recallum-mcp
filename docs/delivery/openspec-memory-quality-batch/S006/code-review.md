# Code review — S006

**Stage:** 5 code-reviewer  
**Verdict:** pass  
**Bounce to:** none

## Reasons
- Usage voter is competition-ranked, skipped at weight 0. Default `recall_usage_weight=0.0`.
- `--usage-weight` reaches a copied `MemoryService` and `report.tunables`.
- Eval is documented as distinct from the workflow evaluator.
- Experiment keeps the production default at 0.0 (MRR 0.82 → 0.79 → 0.78).

## Findings
None material.

## Gaps
Did not re-run pytest or the real-stack pair (stage 8 will run the unit lane).
