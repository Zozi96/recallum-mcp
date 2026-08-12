## 1. Domain: related_memories and reconfirm

- [x] 1.1 Add `RelatedMemory`, `RelatedMemoriesResult`, and `ReconfirmResult` schemas (no `user_id`)
- [x] 1.2 Add repository `related_to` (seed-centered cosine neighbors, same-model, `graph_min_similarity`, exclude seed) and mirror it on the fake
- [x] 1.3 Add `MemoryService.related_memories` (clamp limit to `graph_max_neighbours`; empty list for unknown/foreign/retired) and `MemoryService.reconfirm` (wrap `mark_reconfirmed`, rebuild profiles, `reconfirmed=false` for unknown/foreign/retired)

## 2. MCP surface

- [x] 2.1 Register tools `related_memories` and `reconfirm` with Bearer identity only
- [x] 2.2 Register prompts `session-start`, `capture-scan`, and `stale-review` with compact English guidance and no user selectors
- [x] 2.3 Allowlist exactly those three prompt names in `validate_only_tools_are_exposed`; fail on any other
- [x] 2.4 Update FastMCP `INSTRUCTIONS` for the new tools, prompts, and prefer-`reconfirm` stale path

## 3. Plugin adherence

- [x] 3.1 Update `recallum-memory` skill: eleven tools; optional `related_memories`; prefer `reconfirm`; suggest the three prompts when the client supports them
- [x] 3.2 Update SessionStart suffix in `recallum_hook.py` with the same three points, keeping the reminder short
- [x] 3.3 Bump plugin patch version 0.11.2 → 0.11.3 in manifests, marketplace, and plugin index

## 4. Tests and validation

- [x] 4.1 Unit tests: related neighbors (cross project/category, isolation, limits, unknown seed); reconfirm (own/foreign/retired)
- [x] 4.2 MCP tests: eleven tools; exactly three prompts; startup validation rejects extra prompts; no user selectors
- [x] 4.3 Plugin contractual tests for skill + SessionStart (related_memories, reconfirm, prompt names)
- [x] 4.4 `openspec validate mcp-agent-memory-workflows --strict`, focused pytest, plugin tests, ruff on touched Python
