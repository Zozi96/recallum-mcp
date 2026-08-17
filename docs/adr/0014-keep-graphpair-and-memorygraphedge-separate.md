# ADR 0014: Keep `GraphPair` and `MemoryGraphEdge` separate

## Status
Accepted

## Context
Both are `{source_id, target_id, similarity}`. `GraphPair` is the repo snapshot DTO; `MemoryGraphEdge` is the public Pydantic/OpenAPI type.

## Decision
Do not collapse them. Service maps after the shared degree cap and canonicalizes ids by `str`.

## Alternatives considered
- Reuse `MemoryGraphEdge` inside the repo: rejected; that pulls the HTTP schema into persistence.
- Expose `GraphPair` on the wire: rejected; OpenAPI and self-service already serialize `MemoryGraphEdge`.

## Consequences
Internal snapshot shape can change without a web contract change. Mapping stays in `memory_graph`.
