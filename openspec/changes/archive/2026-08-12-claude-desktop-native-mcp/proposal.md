## Why

Claude Code **Desktop** (`entrypoint: claude-desktop`) loads the Recallum plugin’s hooks and skills but **does not register** the plugin-bundled HTTP MCP server (`plugin:recallum-memory:recallum`) into the session tool catalog. `ToolSearch` then returns **0 results** for `recallum`, `+recallum`, and exact `select:mcp__plugin_recallum-memory_recallum__*` names — even though the same install works in the **CLI**. This is the same class of host limitation we already solved for Grok (native MCP entry; plugin `${user_config.*}` is not enough) and Cursor (literal desktop-safe MCP config).

## What Changes

- **Install Claude with a native user MCP entry** (in addition to the existing plugin): write `mcpServers.recallum` into the Claude user MCP store (`~/.claude.json` / equivalent) with a real `/mcp/` URL and desktop-safe auth, mirroring Grok/Cursor dual-write.
- **Keep the plugin** for marketplace install, hooks, skills, and CLI `userConfig` path; do not remove plugin-bundled `.mcp.json`.
- **Teach agents both Claude tool prefixes** when both can exist: plugin-namespaced `mcp__plugin_recallum-memory_recallum__*` and native `mcp__recallum__*`. Session hook + skill/docs tell the model to discover with ToolSearch (`+recallum` / `select:…`) and call whichever prefix is present.
- **Installer verification and force-replace** for the native Claude MCP definition (`--force-mcp` when mismatched).
- **Docs / setup skill / README troubleshooting**: Desktop vs CLI diagnosis (hooks alone ≠ tools), false green from shell `claude mcp list` inside Desktop, and the dual-prefix ToolSearch recipe.
- **Tests** for installer Claude native MCP write/match/force and hook dual-prefix hints.
- Not in scope: fixing Anthropic’s Desktop host; changing server auth or tool schemas; removing plugin MCP for pure-CLI users.

## Capabilities

### New Capabilities

- `claude-desktop-mcp`: Client-side guarantee that Claude Code (Desktop and CLI) can discover and invoke Recallum tools after install, including a native user MCP registration that does not depend solely on plugin `${user_config.*}` expansion inside Claude.app.

### Modified Capabilities

- (none at server product-spec level; server `/mcp/` contract unchanged)

## Impact

- `plugins/recallum-memory/scripts/install.sh` — Claude install path: dual-write native MCP + verify/force.
- `plugins/recallum-memory/hooks/recallum_hook.py` — Claude tool naming / lookup hints for dual prefixes.
- `plugins/recallum-memory` skill, setup skill, README, `docs/clients.md` as needed.
- `plugins/recallum-memory/tests/test_plugin.py` — installer + hook coverage.
- User machine state after reinstall: `~/.claude.json` gains `mcpServers.recallum` (mode/permissions consistent with existing secrets there); plugin remains under `~/.claude/plugins/`.
- CLI sessions may expose **both** plugin and native tool sets until/unless the host de-duplicates; agents must not assume a single prefix.
- No server deploy or API change.
