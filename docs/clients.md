# Configuring MCP Clients (Cursor, Grok Build, Codex, Claude Code, Devin CLI, and Antigravity CLI)

Recallum speaks MCP over Streamable HTTP at `https://<host>/mcp/`. Every client
needs its own API key (issued with `recallum-admin issue-key`). Keys are per
user; never share one between people.

## Tool surface

The server exposes fifteen MCP tools: `remember`, `remember_batch`, `recall`,
`context`, `get_memory`, `list_memories`, `update`, `merge_memories`,
`related_memories`, `reconfirm`, `forget`, `save_skill`, `match_skills`,
`get_skill`, and `forget_skill`. The last four store versioned procedures
(skills), a separate entity from memories.

Prefer `plugins/recallum-memory/scripts/install.sh` for Codex, Claude Code, Grok Build,
Devin CLI, and Antigravity CLI. Cursor uses its native marketplace and Settings flow below. Keep credentials in
client-owned settings; do not rely on a shell-only export as the sole GUI strategy, and verify the
setup after restart.

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

## Antigravity CLI

Antigravity CLI ships as `agy`. Install with the bundled installer:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target antigravity --url https://recallum.example.com/mcp/
```

This runs `agy plugin install <dir>` (a local directory path, or an **HTTPS** GitHub URL — `git@…`
SSH form and the `owner/repo` shorthand both fail; `agy` does not accept them) and writes the
`recallum` server natively to `~/.gemini/config/mcp_config.json`.

`--target both` remains Codex + Claude Code only and does **not** include Antigravity CLI; you must
pass `--target antigravity` explicitly. The installer's `--remote` flag does not currently cover the
Antigravity target.

**The API key is stored in cleartext.** Antigravity performs no environment-variable expansion in
`mcp_config.json` (unlike Codex/Grok's `${VAR}` references), so a `${RECALLUM_API_KEY}`-style
placeholder will **not** work there — the installer writes the literal bearer token to
`~/.gemini/config/mcp_config.json`. The installer sets that file to mode `0600` and keeps a backup
of the prior config, and **that backup also contains the key in cleartext**. Treat both the live
file and its backup as sensitive; do not commit them, and understand that anyone who can read either
file has the raw token.

As with every other client, the endpoint must be HTTPS with the exact `/mcp/` path; plain HTTP is
accepted only for `localhost`/`127.0.0.1`.

`agy plugin validate plugins/recallum-memory` reports `hooks : 1 processed`. **This is validation
acceptance only — it is not evidence that the hook ever dispatches.** `agy` gates every session
behind interactive Google OAuth sign-in before any session-start hook, hook dispatch, or MCP tool
surface becomes reachable, so hook parity with Codex/Claude Code/Grok Build is unconfirmed and must
not be assumed. `agy plugin validate` also reports `skills : 2 processed`. **This is validation
acceptance only — it is not evidence that skill-driven tool discovery works at runtime.** The same
OAuth gate blocks observation of runtime skill loading, so skill-driven discovery, like hook
dispatch, is expected but unconfirmed.

Diagnose with the same read-only doctor used for the other clients:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
```

It reports an `Antigravity CLI` client: whether the `recallum` server entry is present, its
`serverUrl`, the Authorization header (and whether it is an unexpanded `${...}` placeholder, which
is always wrong for Antigravity), the config file's permission mode, and whether the plugin is
listed by `agy plugin list`. If `agy` is not on `PATH`, that last sub-check is skipped, not failed.

## Devin

Devin uses the MCP server `recallum` over Streamable HTTP at `https://<host>/mcp/`.

The installer writes the user-scope MCP config:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target devin --url https://recallum.example.com/mcp/
```

Or add the server manually with the Devin CLI:

```bash
devin mcp add -s user recallum https://recallum.example.com/mcp/ \
  --header "Authorization: Bearer rcl_YOUR_API_KEY"
```

Equivalently, write `~/.config/devin/mcp_config.json` by hand:

```json
{
  "mcpServers": {
    "recallum": {
      "url": "https://recallum.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer rcl_YOUR_API_KEY"
      }
    }
  }
}
```

Tools are named `mcp__recallum__*` (identical to Codex). Devin lists MCP tools directly, so no
`search_tool` or `ToolSearch` lookup step is needed.

Devin plugins are closed beta, so `install.sh` does **not** run `devin plugins install`. If your
Devin build supports plugins, you can install the recallum-memory skill manually and optionally
wire `.devin/hooks.v1.json` for `SessionStart`. Plugin-hook dispatch is expected but unconfirmed,
so do not rely on it for context injection.

Diagnose with the same read-only doctor used for the other clients:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
```

It reports a `Devin CLI` client: whether the `recallum` server entry is present in
`~/.config/devin/mcp_config.json`, its `url`, the Authorization header (and whether it is an
unexpanded `${...}` placeholder, which is wrong for Devin because environment-variable expansion
in `mcp_config.json` headers is not documented), and the config file's permission mode.

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
Available Tools; Devin CLI uses `mcp__recallum__*`. Antigravity CLI's tool-name prefix is **not yet
determined** — no prefix constant exists in `recallum_hook.py` — so prefer skill-driven tool
discovery over assuming a specific prefix string when working in Antigravity CLI.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Tool call fails with "authentication required" | Missing `Authorization: Bearer` header |
| Tool call fails with "invalid or revoked API key" | Key typo or revoked — issue a new one |
| Grok MCP target is `${user_config.mcp_url}` | Grok does not expand Claude userConfig; run `install.sh --target grok` |
| Devin tool calls fail with "authentication required" | Devin does not document `${RECALLUM_API_KEY}` expansion in `mcp_config.json`; write the literal Bearer token or re-run `install.sh --target devin` |
| `recall` returns `mode: degraded_textual` | Ollama unreachable; check `readyz` and the ollama service |
| Client times out | MCP endpoint is `/mcp/` (trailing slash); HTTPS only via Traefik |
