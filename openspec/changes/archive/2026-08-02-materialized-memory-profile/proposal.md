## Why

Session bootstrap today ranks active memories by importance (plus optional focus), so durable preferences and constraints compete for the same budget as project facts and can be crowded out or missed when they are not semantically close to the task. SuperMemory-style always-on profiles solve this by materializing a stable slice of who the user is; Recallum needs the same power without auto-writing memories or expanding the MCP tool surface. This is the first slice of a larger memory-hardening plan: amplify reads, keep the agent as the only write authority.

## What Changes

- Persist a **materialized memory profile** per user (and optionally per project): static and dynamic slices derived only from existing active memories—no invented facts, no chat LLM required for v1.
- Rebuild the profile on memory lifecycle writes that affect eligibility (`remember`, reconfirm path, `update`/`supersede`, `merge`, `forget`) and via a safety-net path if a read finds it missing or stale.
- Change `context` so the profile slice is **always included first** and is **not evicted** by the focus hybrid selection or the ordinary importance ranking within the shared character budget (profile has its own reserved sub-budget, then the rest of the budget behaves as today).
- Expose the profile for inspection without a new write tool: include a compact profile block in the `context` response, and add a read-only MCP resource (and matching self-service GET) for the raw profile.
- Record profile provenance (`built_at`, version/content hash, source memory ids) so clients and hooks can detect staleness.
- **No** new write tools, **no** server-side conversation extract, **no** entity graph, **no** task scope in this change (those remain later slices).

## Capabilities

### New Capabilities

- `memory-profile`: Materialized always-on profile derived from a user's active memories (selection rules, rebuild triggers, isolation, budget, and read surfaces).

### Modified Capabilities

- `agent-memory-retrieval`: `context` must prepend the materialized profile under a reserved budget and report profile metadata; focus and importance selection must not displace the profile slice.
- `mcp-agent-integration`: MCP exposes a read-only profile resource (and documents the enriched `context` payload) without adding write tools.
- `web-self-service-api`: Authenticated self-service can read the owner's materialized profile.
- `agent-session-bootstrap`: Session guidance/digest path may consume profile-backed context; fail-open behavior unchanged.

## Impact

- **Server**: new persistence for profiles (migration + repository), rebuild logic in the memory service, changes to `context` assembly and response schema.
- **MCP**: new read-only resource; tool names and write contracts unchanged; `context` response shape gains profile fields (additive, not **BREAKING** if clients ignore unknown fields—document as additive).
- **Web self-service**: new GET endpoint for profile inspection.
- **Plugin/hooks**: optional use of richer `context`/resource for digest; no mandatory hook rewrite if profile is already inside `context`.
- **Deps**: no new LLM or external services; rebuild is rule-based over existing memory rows and usage/freshness fields.
- **Out of scope**: entity linking, multi-hop recall boost, task-scoped memory, client extract skill overhaul, auto-forget.
