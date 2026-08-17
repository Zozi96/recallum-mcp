# Code review — S003

**Stage:** 5 code-reviewer  
**Verdict:** pass  
**Bounce to:** none

## Reasons
- Thin HTTP adapter over `MemoryService`; new routes delegate with the session user id.
- Isolation matches domain hide-rules: related → 200 empty list; reconfirm/merge → 404 `"Memory not found"` for unknown/foreign/retired.
- No embedding/`content_hash` on response types.
- Neighbour cap is service `_clamp_limit(..., graph_max_neighbours)`.
- `/memories/merge` registered before `{memory_id}`.
- OpenAPI documents the new operations.

## Findings
None material.

## Gaps
- OpenAPI has no 404s app-wide (pre-existing).
- Integration bound is trivial (one neighbour).
- HTTP suite does not hit merge active-duplicate 409 or merge `EmbeddingError` 503.
