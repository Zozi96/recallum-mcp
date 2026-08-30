## Context

See proposal.md. Runtime already matches the intended contract: `recall_vector_min_similarity` defaults to `None`, applies only in the vector SQL predicate, and is not an MCP argument. The lie is the published requirement plus the limits comment that still calls a measured default “pending”.

## Goals / Non-Goals

**Goals:**
- Make the spec describe current, measured behavior.
- Replace the stale “calibration pending” comment so the next reader does not treat `None` as unfinished work.

**Non-Goals:**
- Ranking, RRF weights, FTS AND, embedding-model swap, turning a Vmin on, eval/dataset changes.

## Decisions

### Spec-only product change; one comment in code
The tests already pin default `None` and vector-leg-only filtering. No retrieval logic changes. Alternative considered: also ship a ranking lever in this change. Rejected: that is a different product bet and would re-open conversational-query risk.

### Keep the optional floor
Do not remove `recall_vector_min_similarity`. Eval CLI still needs an override to re-run a matrix. Alternative: delete the knob. Rejected: losing the measured off-switch wastes the eval path without simplifying the contract.

## Risks / Trade-offs

- [The spec now admits fused noise] → Honest; density remains a future ranking change, not a silent Vmin default.
- [Someone reads “MAY apply a floor” as permission to pick 0.35] → Spec forbids intuition; pin + comment state the evaluator backed `None`.

## Migration Plan

None. Archive syncs the main spec. Production behavior unchanged.

## Open Questions

None.
