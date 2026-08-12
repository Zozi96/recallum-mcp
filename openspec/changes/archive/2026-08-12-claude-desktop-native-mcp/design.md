## Context

See proposal.md for motivation and field evidence (Desktop deferred catalog lacks all `plugin_recallum*` tools while hooks still fire; CLI registers nine tools under `mcp__plugin_recallum-memory_recallum__*`).

Current Claude install path (`install_for_claude`):

- Marketplace + plugin only; MCP lives in plugin `.mcp.json` with `${user_config.mcp_url}` and `Bearer ${user_config.api_token}`.
- Installer writes `pluginConfigs…mcp_url` and optional `pluginSecrets…api_token`.
- Explicit comment that there is **no** separate `claude mcp add` step.

Precedents already in this installer:

| Client | Problem | Fix |
| --- | --- | --- |
| Grok | Does not expand plugin `${user_config.*}` | Native `~/.grok/config.toml` MCP with `Bearer ${ENV}` |
| Cursor | Desktop does not expand env / Configure UI weak | Mode-600 `~/.cursor/mcp.json` with real URL + Bearer (literal when key stored) |
| Claude CLI | Works | Plugin userConfig only |
| Claude Desktop | Plugin MCP not in tool catalog | **Missing native dual-write (this change)** |

Constraints:

- Never put the API key on argv (`claude --config api_token=…` is forbidden).
- Key sources remain: file / env / prompt → `pluginSecrets` + optional env file.
- Claude Desktop GUI often lacks shell exports; env-only auth is insufficient for Desktop (same reason Cursor uses literal Bearer).
- Plugin must stay for hooks/skills; half-loaded “inline” plugin already documented when marketplace is missing.

## Goals / Non-Goals

**Goals:**

- After `install.sh --target claude`, both CLI and Desktop sessions can discover Recallum tools via ToolSearch without relying only on plugin MCP registration.
- Desktop-safe auth for the native entry when a key is stored at install time.
- Agents instructed to use whichever tool prefix is actually present.
- Idempotent install with `--force-mcp` when the native definition differs.

**Non-Goals:**

- Changing FastMCP tool schemas, auth middleware, or `/mcp/` contract.
- Disabling or deleting plugin `.mcp.json` for all hosts (CLI may still use it).
- Forcing users off the plugin marketplace.
- Guaranteeing Anthropic de-duplicates two simultaneous MCP connections.
- Shipping a macOS launchd agent for `RECALLUM_API_KEY` (env file remains best-effort).

## Decisions

### 1. Dual-write native user MCP for Claude (same pattern as Grok)

**Choice:** On Claude install, after plugin install + userConfig verify, also ensure a user-scoped MCP server named `recallum` exists with:

- `type: http`
- `url: <normalized /mcp/ endpoint>`
- `headers.Authorization: …` (see decision 2)

**Where:** Prefer the same store CLI already uses for user MCP (`~/.claude.json` → top-level `mcpServers`), which Desktop sessions already honor for `codegraph` and `richai`. Implementation may use `claude mcp add/remove` when the CLI reliably writes that store, or a guarded JSON merge (Cursor-style) if `claude mcp add` is unsuitable for secrets.

**Why not only fix plugin `.mcp.json`?** Desktop fails *before* tools enter the deferred catalog; unexpanded placeholders or host skip of plugin HTTP MCP cannot be fixed from plugin files alone. Grok already requires a native entry for the same class of host gap.

**Why keep the plugin MCP?** Hooks, skills, marketplace updates, and working CLI sessions continue to depend on the plugin. Removing plugin MCP would be a larger, riskier change and break the documented plugin-only flow.

### 2. Desktop-safe Authorization header

**Choice:**

- When an API key was resolved and stored this run (or is available to the installer without printing it): write **literal** `Bearer <key>` into the native Claude MCP entry, with file mode **600** on `~/.claude.json` if we touch that file (same posture as Cursor `mcp.json` and existing secrets already present for other servers).
- When `--no-store-api-key` and only an env var name is intended: write `Bearer ${RECALLUM_API_KEY}` (or `--token-env-var`) so terminal-launched Claude can expand it; document that Desktop GUI may still need a stored key or re-run without `--no-store-api-key`.
- Always continue writing Claude `pluginSecrets` as today for the plugin path.

**Why not env-only for everyone?** Claude.app launched from Finder/Dock does not inherit the user’s interactive shell; Cursor already taught us env expansion is unreliable for desktop hosts.

**Why not only pluginSecrets?** That path is exactly what Desktop is not turning into registered tools today.

### 3. Dual tool prefixes in agent-facing text

**Choice:** For Claude-oriented hints (hook when `CLAUDE_PLUGIN_ROOT` / Claude path, skill table, setup skill, README):

- Primary discovery: ToolSearch with `+recallum` or exact `select:` of known names.
- Accept **either** `mcp__plugin_recallum-memory_recallum__<tool>` **or** `mcp__recallum__<tool>`.
- Do not instruct a blind call of only the long plugin name (already known to produce `No such tool available` when deferred/missing).

**Why not rename the native server** to force the long plugin id? User MCP names become `mcp__<server>__<tool>`; we cannot recreate the plugin namespace without the plugin server. Short `recallum` matches Codex/Grok mental model and ToolSearch `+recallum`.

### 4. Match / force semantics

**Choice:** Treat native Claude MCP as matching when URL equals the install URL (trailing slash normalized) and Authorization is either the expected env form or a non-empty Bearer (do not re-print or re-compare full secret values in logs). If different URL or missing server → rewrite with `--force-mcp` (or always rewrite when missing). Same error style as Grok/Cursor when different and force not set.

### 5. Duplicate tools on CLI

**Choice:** Accept that healthy CLI may list both plugin and native tool sets (up to 18 deferred names). Prefer documenting dual prefix + ToolSearch over uninstalling plugin MCP.

**Alternative rejected:** Remove or rename plugin `.mcp.json` on install — would fix duplication but regress pure-plugin flows and surprise users who only reconfigured via `/plugin configure`.

### 6. Marketplace “0.11.1 → 0.7.0” noise

**Choice:** Out of critical path. Optionally note in troubleshooting that Desktop’s NativeMarketplaceReader can report a bogus downgrade for directory marketplaces; do not block install. A follow-up may pin marketplace metadata if a schema field is confirmed.

## Risks / Trade-offs

- **[Risk] Two MCP connections on CLI (double traffic / deferred noise)** → Mitigation: dual-prefix docs; optional later cleanup; tools remain correct.
- **[Risk] Literal key in `~/.claude.json`** → Mitigation: mode 600; same class of risk already accepted for Cursor and existing third-party MCP entries; never echo key; prefer store-at-install over argv.
- **[Risk] `claude mcp add` stores secrets in process list** → Mitigation: prefer file merge / stdin patterns that avoid putting the key in argv; document if CLI flags are unsafe.
- **[Risk] Desktop still fails for other reasons (network, TLS)** → Mitigation: setup skill checks ToolSearch / deferred presence, not only `claude mcp list` from a nested shell.
- **[Risk] Hook still names only the long prefix if update is incomplete** → Mitigation: tests assert both prefixes appear on Claude hint path.
- **[Trade-off] Installer complexity** → Accepted; Grok/Cursor already pay this cost for desktop-class hosts.

## Migration Plan

1. Land installer + hook + docs + tests in this repo; bump plugin patch version (e.g. 0.11.1 → 0.11.2) if the shipped plugin package text changes.
2. Users re-run:
   ```bash
   plugins/recallum-memory/scripts/install.sh --target claude --force-mcp
   ```
   (with key available via env, file, or prompt).
3. Fully quit Claude.app and start a **new** Desktop Code session in the project.
4. Validate: ToolSearch `+recallum` or `select:mcp__recallum__context` returns tools; optional CLI still works with either prefix.
5. Rollback: remove user MCP `recallum` (`claude mcp remove recallum` or delete that key from `mcpServers`); plugin-only behavior returns (CLI OK, Desktop likely still broken — known prior state).

## Open Questions

None that block implementation. If `claude mcp add --header` is observed to put secrets in argv on the user’s Claude version, implement file-merge only and cover that path in tests with a fake home.
