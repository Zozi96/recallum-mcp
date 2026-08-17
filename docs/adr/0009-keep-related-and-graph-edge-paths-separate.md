# ADR 0009: Keep `related_to` and graph edge strategies separate

## Status
Accepted

## Context
S007 asked to align `related_to` with bounded graph semantics. `related_to` is already a per-node kNN from one seed. `graph_snapshot` builds an undirected projection (pairwise default, optional LATERAL kNN) and reports `edge_total` / `edges_truncated`.

## Decision
Do not merge `related_to` into `graph_snapshot`, and do not collapse pairwise and scalable SQL into one path. Share only `_cap_pairs_by_degree` and `_scalable_edges_enabled`. Leave `related_to` on its existing seed query; S007 verified it already honors the threshold and cap.

## Alternatives considered
- Drive neighbours from the graph snapshot: rejected; a star from one seed is not a capped undirected projection.
- Always use the LATERAL path: rejected; the default must stay pairwise for small corpora.

## Consequences
Activation flag/threshold affect only `graph_snapshot`. Neighbour reads stay cheap and independent of projection routing.
