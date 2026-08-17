# S007 — Scalable bounded graph edges behind an opt-in flag, preserving honest truncation

## Actor
A memory owner requesting a graph projection or related neighbours; an operator enabling the scalable path.

## Objective and motivation
`graph_snapshot` computes edges with a pairwise O(n²) self-join under a conservative node ceiling (`graph_max_nodes` up to 2000, default 1000). That is correct today but becomes a hard ceiling as a user approaches that volume. The upgrade named in the code is per-node bounded kNN/ANN edges: same minimum similarity, same embedding model, no artificial edges, and an honest truncation signal — with the pairwise path preserved by default.

## In scope
- Choose the kNN/ANN strategy on pgvector for per-node neighbours under `graph_max_neighbours` (prefer a bounded order-by-distance query over the already-selected node subset using the existing embedding index before requiring any new index).
- Activation contract: commit to both mechanisms from the change design — an explicit operator config flag AND a configurable node-count threshold, each independently able to route the projection to the scalable path. Default is flag off with a threshold above any realistic default volume, so the pairwise path remains the effective default.
- Implement the bounded per-node edge path in `graph_snapshot`; align `related_to` where it shares the same semantics.
- Preserve honesty: `graph_min_similarity` threshold, comparability only between embeddings of the same model, no decorative or invented edges.
- Edge-truncation signal: `MemoryGraphResponse` gains two fields. `edge_total` = the number of qualifying undirected pairs above `graph_min_similarity` with matching embedding model, before the per-node `graph_max_neighbours` cap is applied. `edges_truncated` = true when at least one qualifying pair was dropped because an endpoint reached the cap, false otherwise. `total` keeps its existing meaning: the total active node count under the current filters.
- Tests: edge parity on small fixtures between the scalable path and pairwise (edge sets and both new signals identical); dense-component truncation; no invented neighbours under the threshold; graph unit/integration suite green.
- Document in operations/runbook when to activate the scalable path.

## Out of scope
- Graph UI redesign; a full-graph MCP tool; recall ranking changes.
- Removing the presented-node ceiling (`graph_max_nodes` still bounds the projection).
- Forcing a new pgvector index (IVFFlat/HNSW) on all deployments.
- Changing the meaning of the existing `total`/`truncated` node-level fields.

## Mapped OpenSpec tasks
Source change: `scale-memory-graph-edges` — tasks 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2.

## Dependencies
No story dependency. Builds on the existing `MemoryRepository.graph_snapshot` / `related_to`, `MemoryLimits` graph tunables, and `MemoryGraphResponse`.

## Acceptance criteria
- A config flag and a configurable node-count threshold both exist. With the flag off and the node count under the threshold, `graph_snapshot` returns the same edge set, `edge_total`, `edges_truncated`, `total`, and `truncated` as the current pairwise path on the same fixtures.
- Activation is tested for both mechanisms independently: setting the flag routes to the scalable path even under the threshold, and exceeding the threshold routes to it even with the flag off; with neither active, the pairwise path is used.
- With the scalable path enabled, every returned edge satisfies `graph_min_similarity` and both endpoints carry the same embedding model; a fixture where a node's qualifying relations are all below the threshold yields no invented neighbour for that node.
- In a fixture where one node's qualifying neighbours exceed `graph_max_neighbours`, the response keeps only the strongest edges within the limit, reports `edges_truncated: true`, and reports `edge_total` as the pre-cap qualifying pair count.
- In a fixture where all nodes fit within the per-node cap, the response reports `edges_truncated: false` and `edge_total` equal to the returned edge count.
- `related_to` (if aligned) honors the same bounded semantics and minimum threshold under the same activation mechanisms.
- Graph tests pass: small-fixture parity compares the scalable and pairwise edge sets plus both new signals exactly, truncation/density tests cover the dense case, and the graph unit/integration suites are green.
- Operations/runbook documentation states the activation conditions (explicit operator flag and/or node volume above the threshold) and that the default deployment keeps the pairwise path.

## Assumptions
- The two new public field names `edges_truncated` and `edge_total` on `MemoryGraphResponse` are committed contract for this story, since downstream Gherkin and QA assert them.
- The internal repository snapshot (`GraphSnapshot` in `recallum/db/repositories/memory_repo.py`) carries the pre-cap qualifying edge count so `edge_total` is reportable in both the pairwise and scalable paths; the internal field name is an implementation choice.
- The strategy is a per-node bounded nearest-neighbour query over the already-selected bounded node subset using the existing pgvector embedding index; no new index is required by this change (index cost is measured, not assumed).
- "Align `related_to`" is a verification-and-consistency task: `related_to` is already a per-node bounded query, so the story aligns semantics rather than rewriting it.

## Open questions
- None blocking. The activation threshold value and the internal `GraphSnapshot` field name are implementation choices unless the team specifies them.

## Affected surface
`recallum/memory/schemas.py::MemoryGraphResponse` (new `edges_truncated` and `edge_total` fields), `recallum/db/repositories/memory_repo.py` (`graph_snapshot`, `related_to`, `GraphSnapshot` carrying the pre-cap qualifying edge count), `recallum/memory/service.py::memory_graph`, `recallum/memory/limits.py` and `recallum/config.py` (activation flag/threshold), `openapi/web-v1.json` snapshot (the `/me/memory-graph` endpoint serializes `MemoryGraphResponse`), `tests/contract/memory_repository.py`, `tests/unit/test_service.py`, `docs/operations.md` and runbook notes.

## Risks
Edge-quality divergence between the two paths → parity tests on small fixtures, including the new signals. Index/query cost on large corpora → measure before any new index requirement; the bounded-subset query avoids it for this change. Silent edge drops becoming invisible again → `edges_truncated`/`edge_total` make truncation observable.

## Validation expectations
Graph unit/integration suite green; parity and truncation tests asserting the new fields; activation tests for both mechanisms; runbook note reviewed as delivery evidence.

## Boundary crossings
Memory-graph capability. RLS, auth, and exposed content are unchanged.
