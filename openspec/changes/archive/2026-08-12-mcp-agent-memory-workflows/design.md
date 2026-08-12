## Context

See `proposal.md` for motivation. The MCP server already exposes nine tools plus `recallum://profile`. `validate_only_tools_are_exposed` currently fails if any prompt is registered. Thematic edges live in `MemoryService.memory_graph` / `graph_snapshot` (stored embeddings, same-model cosine, `graph_min_similarity`, `graph_max_neighbours`) and are web-only. Identical re-`remember` already stamps `reconfirmed_at` via `mark_reconfirmed`; agents have no id-based way to do that. Plugin SessionStart already teaches start → semantic `recall` → capture.

## Goals / Non-Goals

**Goals:**

- Project seed-scoped thematic neighbors onto MCP without dumping the graph or embeddings.
- Stamp freshness by id using the existing repository path.
- Allowlist exactly three workflow prompts; fail startup on any other prompt name.
- Teach skill and SessionStart the new loop without lengthening the hook into a second skill.

**Non-Goals:**

- Profile pin/unpin, export/import, ranking, telemetry, `recall_usage_weight`, auth changes.
- Exposing `memory_graph` as an MCP tool.
- Changing web graph semantics or persisting edges.
- Archiving other OpenSpec changes.

## Decisions

### 1. Seed-centered neighbors, not a filtered global snapshot

`graph_snapshot` selects the top-N memories by importance, so a low-importance seed can be absent from that projection. `related_memories` therefore queries neighbors of one active seed: other active memories of the same user, same known `embedding_model`, cosine similarity at or above `graph_min_similarity`, ordered strongest-first, excluding the seed. Category, scope, and project do not filter (same thematic rule as the web graph). `similar_active` stays the remember-time same-bucket check and is not reused.

Unknown, foreign, and retired seeds return an empty neighbor list (same isolation as `get_memory` / `forget`: no existence leak). Incomparable provenance (missing or mismatched model) yields no neighbors. Limit defaults to `graph_max_neighbours` and is clamped to that ceiling. No dedicated `MemoryLimits` field unless tests prove the graph cap is too tight for agents.

Response shape: `memory_id` plus `related` items with `id`, `content`, `category`, `scope`, `project`, `similarity`. No embeddings.

Alternative rejected: filter `memory_graph` edges to the seed — misses seeds outside the node cap and ships a larger payload than agents need.

### 2. `reconfirm` is a thin service over `mark_reconfirmed`

`MemoryService.reconfirm(user_id, memory_id)` calls `mark_reconfirmed`, rebuilds profiles for the stamped row (same as the identical-remember path), and returns `ReconfirmResult(reconfirmed, memory)`. Unknown, foreign, and retired ids return `reconfirmed=false` and `memory=None`. Content is not rewritten; embeddings are not recomputed.

### 3. Exactly three argument-light prompts

Register FastMCP prompts named `session-start`, `capture-scan`, and `stale-review`. Bodies are compact English agent guidance (call `context` with project/focus; capture via `remember_batch`; stale queue via `list_memories(stale=true)` then `reconfirm` / `update` / `forget` / `merge_memories`). Optional string args such as `project` or `focus` are allowed; no user selectors. `validate_only_tools_are_exposed` allowlists those three names and fails on any other. Missing allowlisted prompts on the real server are caught by discovery tests, not by requiring every test FastMCP to register them.

### 4. Plugin teaches; hook stays a suffix

Skill documents eleven tools, optional `related_memories` after a useful `recall`/`context` hit when exploring a thematic neighborhood (not every recall), prefer `reconfirm` over identical re-`remember` for the stale queue, and suggest the three prompts when the client supports MCP prompts. SessionStart adds a short suffix covering those three points without duplicating the skill. Plugin patch version bumps (0.11.2 → 0.11.3) across manifests and marketplace index.

## Risks / Trade-offs

- [Seed query scans more rows than the bounded graph snapshot] → Same min-similarity and neighbour cap; one seed vs all active rows of that user, not pairwise among 200 nodes.
- [Clients without prompt support ignore prompts] → Tools remain complete; skill/hook still describe the loop.
- [Empty related list conflates “no neighbors” with “unknown id”] → Matches forget/get isolation; do not add a `found` flag that would leak ownership.

## Migration Plan

Additive MCP surface. Existing clients keep working. Plugin bump is the client-facing release. Rollback: revert the change; no schema migration.

## Open Questions

None.
