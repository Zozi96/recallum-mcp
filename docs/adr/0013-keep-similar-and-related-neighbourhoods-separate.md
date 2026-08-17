# ADR 0013: Keep write-time `similar` distinct from read-time `related`

## Status
Accepted

## Context
S002/S003 both talk about neighbours. `similar_active` is a write-time advisory at `similar_min_similarity` (0.85) in the same scope/project bucket. `related_to` is a read-time thematic star at `graph_min_similarity` (0.72). Schemas (`SimilarMemory` vs `RelatedMemory`) carry different fields.

## Decision
Do not merge the queries, thresholds, or response types.

## Alternatives considered
- One neighbour helper parameterized by threshold: rejected; they already differ in visibility, exclusion rules, and fail-open vs empty-list contracts, and will keep diverging.

## Consequences
Hygiene guidance can say "read `similar`" without implying graph neighbours. Graph/related changes cannot retune the write-time advisory.
