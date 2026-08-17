# ADR 0008: Share the competition-rank vote for importance and usage

## Status
Accepted

## Context
S006 wired `recall_count` as a second RRF voter that must use the same competition-ranking mechanism as importance. Delivery copied the loop. A later change to one voter (tie rank, skip-at-zero-weight) would silently break the required symmetry.

## Decision
Extract `MemoryService._add_competition_vote` and use it for both `recall_importance_weight` and `recall_usage_weight`. Weight 0 still skips the voter entirely.

## Alternatives considered
- Leave the two loops: rejected; S006 requires they stay the same mechanism, and the batch already has two copies.
- Fold usage into the importance sort key: rejected; that would change ranking and mix two signals.

## Consequences
Tie-sharing and RRF contribution stay one implementation. A future voter that must not competition-rank should not call this helper.
