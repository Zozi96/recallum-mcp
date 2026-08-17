# Configuring MCP Clients (Cursor, Grok Build, Codex, and Claude Code)

Recallum speaks MCP over Streamable HTTP at `https://<host>/mcp/`. Every client
needs its own API key (issued with `recallum-admin issue-key`). Keys are per
user; never share one between people.

## Tool surface

The server exposes eleven MCP tools: `remember`, `remember_batch`, `recall`,
`context`, `get_memory`, `list_memories`, `update`, `merge_memories`,
`related_memories`, `reconfirm`, and `forget`.

Prefer `plugins/recallum-memory/scripts/install.sh` for Codex, Claude Code, and Grok Build. Cursor
uses its native marketplace and Settings flow below. Keep credentials in client-owned settings;
do not rely on a shell-only export as the sole GUI strategy, and verify the setup after restart.

## Grok Build (no Claude Code required)

Grok has a **native** marketplace index at `.grok-plugin/marketplace.json` and a
plugin manifest at `plugins/recallum-memory/plugin.json`. Discovery does not go
through Claude Code.

Grok does **not** resolve `${user_config.mcp_url}` / `${user_config.api_token}`
in a plugin `.mcp.json`. Register the MCP server natively (same idea as Codex):

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target grok --url https://recallum.example.com/mcp/
# remote registry instead of a local checkout:
# plugins/recallum-memory/scripts/install.sh --target grok --remote
```

Or by hand:

```toml
# ~/.grok/config.toml
[mcp_servers.recallum]
url = "https://recallum.example.com/mcp/"
enabled = true

[mcp_servers.recallum.headers]
Authorization = "Bearer ${RECALLUM_API_KEY}"
```

```bash
grok plugin marketplace add Zozi96/recallum-mcp
grok plugin install recallum-memory --trust
grok plugin enable recallum-memory
grok mcp doctor recallum
```

The TUI marketplace browser can show skills/hooks before install when the repo
ships `.grok-plugin/plugin-index.json`.

## Codex

`~/.codex/config.toml` (or `codex mcp add`):

```toml
[mcp_servers.recallum]
url = "https://recallum.example.com/mcp/"
bearer_token_env_var = "RECALLUM_API_KEY"
```

From the VPS itself, the same endpoint works over the public HTTPS route
(Traefik); no special local configuration is needed — local and remote clients
use the same URL and behavior.

## Cursor

Cursor's native marketplace is rooted at `.cursor-plugin/marketplace.json`; the plugin manifest
uses `.cursor-plugin/plugin.json`, shared skills, a Cursor session hook, and the `recallum` MCP
server. Add the marketplace with the current Cursor CLI:

```bash
agent plugin marketplace add https://github.com/Zozi96/recallum-mcp.git
```

Then run `/add-plugin` in Cursor or enable `recallum-memory` from Settings. Provide the required
`RECALLUM_MCP_URL` (with the exact `/mcp/` path) and `RECALLUM_API_KEY` variables there rather than
putting a literal key in a checked-in config or relying on a shell-only export. Restart Cursor and
verify that the `recallum` server remains enabled without displaying the key. For a one-off local
CLI test, use `agent --plugin-dir /path/to/recallum-mcp/plugins/recallum-memory`.

Cursor's `sessionStart` hook returns context through top-level `additional_context`, but delivery
is best-effort and it cannot run before every prompt. The always-applied rule carries the exact
canonical-project-key fallback. MCP tools are exposed under Available Tools rather than a stable
textual prefix.

## Claude Code

Claude Code keeps the plugin for hooks/skills (`.mcp.json` + `${user_config.*}`) and the installer
**also** dual-writes a native user MCP server into `~/.claude.json` (`mcpServers.recallum`) so
Claude Desktop ToolSearch can find tools under `mcp__recallum__*`.

```bash
plugins/recallum-memory/scripts/install.sh --target claude --url https://recallum.example.com/mcp/
# optional masked plugin fallback:
# /plugin configure recallum-memory@recallum-local
```

Verify:

```bash
claude mcp list | grep recallum   # plugin:recallum-memory:recallum and/or recallum
# Desktop session: ToolSearch +recallum or select:mcp__recallum__context
# Nested shell claude mcp list inside Desktop is not proof of Desktop tool registration
```

## Agent usage guidance

Put a short instruction in each project's AGENTS.md / CLAUDE.md so agents
remember to use the memory tools:

```md
You have persistent memory via the recallum MCP server.
- remember: store durable preferences, decisions, constraints, facts (atomic statements only).
- recall: search memory by meaning or exact terms before asking again.
- context: call at the start of a session on a project.
- update: when a stored fact changes, replace it instead of forgetting and
  re-adding; remember reports similar existing memories in its `similar` field,
  so read those and decide whether the new one supersedes them.
- list_memories / forget: browse and remove your own memories.
Never store full conversations; store the distilled fact.
```

Tool name prefixes differ by client: Codex `mcp__recallum__*`, Claude Code
`mcp__plugin_recallum-memory_recallum__*` and/or `mcp__recallum__*` (native/Desktop), Grok Build
`recallum__*` via `search_tool` / `use_tool`; Cursor uses the Recallum MCP tools listed in
Available Tools.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Tool call fails with "authentication required" | Missing `Authorization: Bearer` header |
| Tool call fails with "invalid or revoked API key" | Key typo or revoked — issue a new one |
| Grok MCP target is `${user_config.mcp_url}` | Grok does not expand Claude userConfig; run `install.sh --target grok` |
| `recall` returns `mode: degraded_textual` | Ollama unreachable; check `readyz` and the ollama service |
| Client times out | MCP endpoint is `/mcp/` (trailing slash); HTTPS only via Traefik |
