# ADR 0007: Share the graph degree-cap algorithm

## Status
Accepted

## Context
S007 added `_cap_pairs_by_degree` so the scalable snapshot stays bounded. `MemoryService.memory_graph` already applied the same greedy per-node cap when mapping pairs to `MemoryGraphEdge`. Two copies of one rule invited silent drift in truncation.

## Decision
Call `_cap_pairs_by_degree` from the service instead of inlining the loop. Keep both application sites: the repo still caps the scalable snapshot; the service still caps the public response (pairwise snapshots remain the full qualifying pair list so `edge_total` is `len(pairs)` by construction).

## Alternatives considered
- Cap pairwise pairs in the repo and drop the service cap: rejected; that changes `GraphSnapshot.pairs` meaning on the default path and is more than algorithm reuse.
- New `memory/graph.py` module: rejected; one pure function does not justify a new layer.

## Consequences
Degree-cap sort, tie-break, and drop rules stay identical across repo, fake, and service. Pairwise vs scalable SQL remains two strategies (see ADR 0009).
