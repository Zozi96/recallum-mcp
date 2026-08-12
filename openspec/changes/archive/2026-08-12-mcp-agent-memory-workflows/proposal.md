## Why

Agents already have a start → pivot → capture memory loop, but the MCP surface still forces them to re-`remember` identical content to stamp freshness and has no seed-scoped thematic neighborhood. Prompts that would encode that loop are currently forbidden at startup.

## What Changes

- Add MCP tool `related_memories(memory_id, limit)`: thematic neighbors of one seed from the same stored-embedding cosine evidence as `memory_graph`, never the full graph and never embeddings.
- Add MCP tool `reconfirm(memory_id)`: stamp `reconfirmed_at` via existing `mark_reconfirmed` without rewriting content; unknown, foreign, and retired ids report `reconfirmed=false`.
- Allow exactly three MCP prompts: `session-start`, `capture-scan`, `stale-review`. Startup validation fails if any other prompt is registered.
- Update `mcp-agent-integration` so the published tool set is the existing nine plus `related_memories` and `reconfirm` (eleven total). Keep identity from Bearer only; no user selectors.
- Teach the plugin skill and SessionStart hook the new loop: optional `related_memories` after a useful hit, prefer `reconfirm` on the stale queue, suggest the three prompts when the client supports them.
- Bump the plugin patch version.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-agent-integration`: eleven tools including `get_memory`, `merge_memories`, `related_memories`, and `reconfirm`; exactly three allowlisted prompts; still no user selectors.
- `agent-memory-lifecycle`: explicit reconfirmation of an active memory by id without a content rewrite.
- `memory-graph`: seed-filtered neighbor projection for agents, using the same similarity evidence as the web graph without exposing the full graph on MCP.
- `agent-session-bootstrap`: SessionStart / skill guidance for prompts, related neighbors, and `reconfirm`.

## Impact

- Server: `recallum/mcp/server.py`, `recallum/memory/service.py`, `recallum/memory/schemas.py`, `recallum/memory/limits.py`, `recallum/db/repositories/memory_repo.py`, fakes, unit/MCP tests.
- Plugin: `plugins/recallum-memory` skill, SessionStart hook, contractual tests, patch version in manifests and marketplace index.
- Out of scope: profile pin/unpin, export/import, ranking, telemetry, `recall_usage_weight`, auth changes, exposing `memory_graph` as an MCP tool, archiving other OpenSpec changes.
