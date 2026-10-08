# Configuring MCP Clients (Cursor, Grok Build, Codex, Claude Code, Devin CLI, Antigravity CLI, Muse Code, Factory Droid, and OMP)

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
Devin CLI, Antigravity CLI, Muse Code, Factory Droid, and OMP. Cursor uses its native marketplace and Settings flow below.
Keep credentials in client-owned settings; do not rely on a shell-only export as the sole GUI strategy,
and verify the setup after restart.

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

Cursor MCP is native `~/.cursor/mcp.json` only (installer `--target cursor`, literal Bearer,
mode 600). The plugin does not register MCP and does not ship `.mcp.json`. Add the marketplace
with the current Cursor CLI:

```bash
agent plugin marketplace add https://github.com/Zozi96/recallum-mcp.git
```

On another host: `git pull`; `install.sh --target cursor --url https://<host>/mcp/`; in Cursor
update marketplace `recallum-local` and plugin `recallum-memory`; fully quit Cursor. Settings →
Tools & MCP must show only `recallum` enabled. Do not print MCP JSON. No Recallum server deploy.

Then enable `recallum-memory` from Settings → Plugins. Restart Cursor and verify `recallum` without
displaying the key. For a one-off local CLI test, use
`agent --plugin-dir /path/to/recallum-mcp/plugins/recallum-memory` (skills/hooks/rules only; MCP
still comes from `~/.cursor/mcp.json`).

Cursor's `sessionStart` hook returns context through top-level `additional_context`, but delivery
is best-effort and it cannot run before every prompt. The always-applied rule carries the exact
canonical-project-key fallback. MCP tools are exposed under Available Tools rather than a stable
textual prefix.

## Claude Code

Claude Code keeps the plugin for hooks/skills only. MCP is the native user server the installer
writes into `~/.claude.json` (`mcpServers.recallum`), which Desktop ToolSearch finds as
`mcp__recallum__*`. The plugin does not ship `.mcp.json`.

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

The installer writes the user-scope MCP config with a bearer reference that Devin resolves from the
environment at connect time. It also persists the key to `~/.config/recallum/env` (mode `600`):

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target devin --url https://recallum.example.com/mcp/
```

The resulting `~/.config/devin/mcp_config.json` contains no secret; the bearer is `Bearer
${RECALLUM_API_KEY}` and is expanded by Devin when it connects.

Or add the server manually with the Devin CLI:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
devin mcp add -s user recallum https://recallum.example.com/mcp/ \
  --header "Authorization: Bearer ${RECALLUM_API_KEY}"
```

Equivalently, write `~/.config/devin/mcp_config.json` by hand:

```json
{
  "mcpServers": {
    "recallum": {
      "url": "https://recallum.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer ${RECALLUM_API_KEY}"
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
`~/.config/devin/mcp_config.json`, its `url`, the Authorization header (`Bearer ${RECALLUM_API_KEY}`
redacted; the variable is checked and reported as set or unset), and the config file's permission
mode.

## Muse Code

Muse Code ships as `muse`. Install with the bundled installer:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target muse --url https://recallum.example.com/mcp/
```

This installs the native `.muse-plugin` bundle (`muse plugins install <dir>`,
skills/hooks only — the manifest declares an empty `mcpServers`), approves both
hook capabilities (hooks stay inactive until approved), and writes the `recallum`
server natively to `${XDG_CONFIG_HOME:-~/.config}/muse/settings.json`
(`mcpServers.recallum`, mode `0600`).

`--target both` remains Codex + Claude Code only and does **not** include Muse Code; you must
pass `--target muse` explicitly. The installer's `--remote` flag does not currently cover the
Muse target (same as Antigravity): the bundle always installs from the local checkout.

**The API key is stored in cleartext.** Muse performs no environment-variable expansion in
`settings.json` headers, so a `${RECALLUM_API_KEY}`-style placeholder will **not** work there —
the installer writes the literal token. Treat the file as sensitive; anyone who can read it
has the raw token. The file must keep `"schema_version": 1`; do not add a second `mcp_servers`
(snake_case) block alongside `mcpServers` — that faults the config.

As with every other client, the endpoint must be HTTPS with the exact `/mcp/` path; plain HTTP is
accepted only for `localhost`/`127.0.0.1`.

Tools are named `mcp__recallum__*` and are listed directly, so no lookup step is needed.
Hook output uses the same `hookSpecificOutput.additionalContext` shape as Claude Code
(verified against Muse Code 1.3.0 with `muse plugins hook test`); the Cursor flat
`additional_context` shape is rejected, so the hook never emits it on the Muse path.

Diagnose with the same read-only doctor used for the other clients:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
```

It reports a `Muse Code` client: whether the `recallum` server entry is present in
`settings.json`, its `url`, the Authorization header (a `${...}` placeholder is always
flagged, even when the referenced variable is set), the file's `schema_version` and
permission mode, and whether the plugin is listed by `muse plugins list` (with version-drift
check). If `muse` is not on `PATH`, that last sub-check is skipped, not failed.

## Factory Droid

Factory Droid ships as `droid`. Install with the bundled installer:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target droid --url https://recallum.example.com/mcp/
```

Two registrations, mirroring Claude Code: the plugin bundle (skills/hooks) and the native
user MCP server. The repo root doubles as the marketplace (Droid falls back to
`.claude-plugin/marketplace.json` when `.factory-plugin/marketplace.json` is absent) and is
registered with `droid plugin marketplace add <repo-root>`. For a local path Droid registers
the **directory basename** — `recallum-mcp` for this checkout, not the manifest name
`recallum-local` — and installs the plugin as
`droid plugin install recallum-memory@<basename> --scope user`.

The native MCP entry is written to `~/.factory/mcp.json` (mode `600`;
`FACTORY_HOME_OVERRIDE` relocates the whole `.factory` tree):

```json
{
  "mcpServers": {
    "recallum": {
      "type": "http",
      "url": "https://recallum.example.com/mcp/",
      "headers": { "Authorization": "Bearer ${RECALLUM_API_KEY}" },
      "oauth": false
    }
  }
}
```

`type` must be `http` and `oauth` must be `false`: without it Droid attempts an OAuth
discovery flow against a header-authenticated server that offers none. Droid expands
`${VAR}` in header values at connect time, so the file holds no secret — the same class as
Devin/Grok. The key itself is persisted to `~/.config/recallum/env` (and on Linux
`~/.config/environment.d/99-recallum.conf` for desktop sessions); with
`--no-store-api-key` nothing is persisted, so export the variable in the environment that
launches `droid`.

`--target auto` includes Droid when `droid` is on `PATH`. `--target both` and `--remote` do
**not** cover this target — the marketplace is always this checkout — and a differing
existing MCP definition requires `--force-mcp`.

Tools are named `recallum___*` (triple underscore). Droid can keep the server deferred, so
if the tools are not listed directly, load them with ToolSearch (`+recallum` or `select:` of
the full name) before concluding they are unavailable.

The shared `hooks.json` wires `SessionStart` (startup|resume|clear|compact) and
`UserPromptSubmit` for Droid, both under a 5 s timeout and failing open. Droid sets
`DROID_PLUGIN_ROOT` (plus a `CLAUDE_PLUGIN_ROOT` compatibility alias) for plugin hooks, but
its value is not a usable path — droid 0.229.0 sets it to
`/PLUGIN_ROOT_NOT_EXPANDED_ERROR` and only expands the literal `${DROID_PLUGIN_ROOT}` token
inside the hooks.json command string, which resolves the hook script from the plugin root.

## OMP

OMP ships as `omp`. Install with the bundled installer:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target omp --url https://recallum.example.com/mcp/
```

This writes the `recallum` server natively to `~/.omp/agent/mcp.json` (or
`$PI_CODING_AGENT_DIR/mcp.json` when that variable is set) with `type: http` and
`Authorization: Bearer ${RECALLUM_API_KEY}`. OMP expands `${VAR}` and `${VAR:-default}` in
native MCP files at discovery time, so the placeholder is the correct shape — the same class
as Codex, Grok, and Devin, not the cleartext class used by Antigravity and Muse. The file is
mode `0600`. Unrelated `mcpServers` entries are preserved. If `recallum` is listed in
`disabledServers`, the installer removes that name: the denylist hides a server from every
source.

`--target both` remains Codex + Claude Code only and does **not** include OMP; you must pass
`--target omp` explicitly. `--remote` does not cover this target.

The installer does not install a plugin and does not register a session hook. OMP's hook
runtime loads JS/TS factories from `.omp/hooks/pre|post/`, not the Claude command hook in
`hooks/hooks.json`. No SessionStart dispatch was observed for this client, so none is claimed.
A project `.omp/mcp.json` entry of the same name wins over the user file; the installer never
writes a project file (it would be committable). A named profile (`omp --profile <name>`) reads
`~/.omp/profiles/<name>/agent/mcp.json` instead of the default agent directory. Set
`PI_CODING_AGENT_DIR` to that profile's agent directory before installing, or the default file
will not be the one the profile loads.

OMP's documented runtime registry names tools `mcp__<server>_<tool>` (oh-my-pi
`docs/mcp-runtime-lifecycle.md`). That predicts `mcp__recallum_context`. This change did not
observe a live Recallum handshake, so treat that spelling as the documented name, not as
measured dispatch. Restart OMP so MCP reloads.

Diagnose with the same read-only doctor used for the other clients:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
```

It reports a `Factory Droid` client: whether the `recallum` server entry is present in
`~/.factory/mcp.json`, its `url`, the Authorization header, `type`/`oauth` correctness, the
config file's permission mode, and the plugin installation record under
`~/.factory/plugins/installed_plugins/` with a version-drift check (the record is read from
disk because `droid plugin list` prints plain text only). After a `git pull`, rerun
`install.sh --target droid` (it refreshes an existing install with
`droid plugin update recallum-memory@<basename>`), then start a new droid session so MCP,
skills, and hooks reload.

It reports an `OMP` client when `mcp.json` exists: whether the `recallum` server entry is
present, its `type` (must be `http`), its `url`, the Authorization header
(`Bearer ${RECALLUM_API_KEY}` redacted; the variable is checked and reported as set or unset),
the file mode, and whether `disabledServers` still hides `recallum`. A missing file is "not
configured", not a failure.

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
Available Tools; Devin CLI uses `mcp__recallum__*`; Muse Code uses `mcp__recallum__*` (listed
directly, no lookup step); Factory Droid uses `recallum___*` (triple underscore, loaded with
ToolSearch when the server is deferred). OMP's documented names are `mcp__recallum_<tool>` (one underscore
between the server and the tool, so `mcp__recallum_context`); that spelling was not observed
against a live handshake. Antigravity CLI's tool-name prefix is **not yet
determined** — no prefix constant exists in `recallum_hook.py` — so prefer skill-driven tool
discovery over assuming a specific prefix string when working in Antigravity CLI.

Current user and repository instructions always take precedence over recalled memory. Phrase every
`recall` query in English; the server does not translate queries or memories, and existing memories
must not be rewritten for language. «¿qué decidimos sobre MemoryService.context?» becomes
`What did we decide about MemoryService.context?`, with the symbol intact. Keep
`MemoryService.context`, `recallum/memory/service.py`, and `uv run pytest` verbatim inside the
English query. Answer the user in their language.

These are MCP tool arguments, not a Python API. `P` is the canonical project key from the session
hook — never invent a key or copy one from another workspace. `scope="project"` requires `project`.
Anchors (`symbol` / `file`) filter before ranking; an empty list can mean no matching anchors, not
that the identifier never appears in text. The no-filter variant (identifier kept in `query` only)
is an option when relevant, not a mandatory second call. A known memory UUID is `get_memory`, not
`symbol`. Mid-task checkpoints use `limit=3`, suppress equivalent queries, and continue fail-open
if Recallum is unavailable.

| Intent | Minimal args |
| --- | --- |
| Project + globals | `recall(query="Context budget decisions", project=P, limit=3)` |
| Project only | `recall(query="Context budget decisions", project=P, scope="project", limit=3)` |
| Globals only | `recall(query="Preferred coding conventions", scope="global", limit=3)` |
| Symbol | `recall(query="Context budget decisions", project=P, symbol="MemoryService.context", limit=3)` |
| File | `recall(query="Context budget decisions", project=P, file="recallum/memory/service.py", limit=3)` |
| Mention without anchor | `recall(query="Decisions about MemoryService.context", project=P, limit=3)` |
| Known UUID | `get_memory(memory_id=M)` |

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Tool call fails with "authentication required" | Missing `Authorization: Bearer` header |
| Tool call fails with "invalid or revoked API key" | Key typo or revoked — issue a new one |
| Grok MCP target is `${user_config.mcp_url}` | Grok does not expand Claude userConfig; run `install.sh --target grok` |
| Devin tool calls fail with "authentication required" | `RECALLUM_API_KEY` is not exported in the shell that launched Devin; run `install.sh --target devin` to persist it to `~/.config/recallum/env` and source that file before launching Devin |
| Muse Code tool calls fail with "authentication required" | `settings.json` holds an inert `${...}` placeholder (Muse does not expand env vars); re-run `install.sh --target muse` with a stored key so the literal token is written |
| Droid tool calls fail with "authentication required" | `RECALLUM_API_KEY` is not exported in the environment that launched `droid`; source `~/.config/recallum/env`, or re-run `install.sh --target droid` without `--no-store-api-key` |
| `recallum___*` tools not listed in Droid | Droid can keep the server deferred — load them with ToolSearch (`+recallum` or `select:`) before concluding they are unavailable; start a new session first |
| OMP tool calls fail with "authentication required" | `RECALLUM_API_KEY` is unset in the environment that launched OMP, or a project `.omp/mcp.json` overrides the user entry; source `~/.config/recallum/env` or re-run `install.sh --target omp` |
| `recall` returns `mode: degraded_textual` | Ollama unreachable; check `readyz` and the ollama service |
| Client times out | MCP endpoint is `/mcp/` (trailing slash); HTTPS only via Traefik |
