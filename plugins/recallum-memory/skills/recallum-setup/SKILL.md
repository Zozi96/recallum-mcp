---
name: recallum-setup
description: Set up or diagnose the Recallum plugin and remote MCP connection for Cursor, Codex, Claude Code, Grok Build, or Antigravity CLI when the user explicitly asks to install, configure, verify, troubleshoot, or test Recallum.
---

# Recallum Setup

Diagnose without exposing credentials. Never print, echo, interpolate, or store an API key value.

Prefer the bundled `scripts/install.sh` for configuration. It validates the endpoint, registers the
repo marketplace, installs the plugin, configures the bearer-token environment variable reference,
and by default **stores the API key** (from `--api-key-file`, the current environment, or a hidden
prompt) so clients can authenticate after install:

- Claude Code → `~/.claude/.credentials.json` `pluginSecrets` (GUI-safe; same as `/plugin configure`)
- All targets → `~/.config/recallum/env` and Linux `~/.config/environment.d/99-recallum.conf`

Never pass the key as `claude --config api_token=...` or as a CLI flag (argv / process list). Use
`--no-store-api-key` to skip persistence. Targets: `--target codex`, `claude`, `grok`, `antigravity`,
`both`, or default `auto`. Run with `--dry-run` first to see the planned actions. `--target both`
means Codex + Claude Code only; it does not include Grok, Cursor, or Antigravity CLI.

Cursor: `install.sh --target cursor` (or `auto` when `cursor-agent`/`agent` is on PATH) registers the
marketplace and writes a mode-600 `~/.cursor/mcp.json` entry. Plugin install is still done in the
Cursor UI (`/plugins` or Settings → Plugins); the CLI cannot install plugins.

Antigravity CLI: `install.sh --target antigravity` runs `agy plugin install <dir>` and writes a
mode-600 `~/.gemini/config/mcp_config.json` entry with a **literal, cleartext** bearer token — see
the dedicated section below before running it.

## Diagnose

ALL status inspection must go through `plugins/recallum-memory/scripts/recallum_doctor.py`. Reading
`~/.cursor/mcp.json`, `~/.claude/.credentials.json`, `~/.config/recallum/env`,
`~/.grok/config.toml`, or any plugin-cache `mcp.json` with `cat`, `head`, `grep`, `python`, or
another raw-file recipe is forbidden: these files interleave ordinary configuration with a literal
bearer token. The doctor is read-only and redacts bearer values in both text and JSON output.

```bash
plugins/recallum-memory/scripts/recallum_doctor.py
plugins/recallum-memory/scripts/recallum_doctor.py --json
```

Use `--token-env-var NAME` for a custom token variable and `--repo-root PATH` for another checkout.
Cursor and the Cursor plugin cache were previously undocumented for inspection, which is how the
credential leak happened.

## Setup — Codex

1. Confirm the plugin marketplace and installation:
   `codex plugin marketplace list --json` must contain `recallum-local` at this repository root,
   and `codex plugin list` must show `recallum-memory`.
2. Run the read-only doctor for safe MCP fields, environment status, permissions, and version drift:

   ```bash
   python3 plugins/recallum-memory/scripts/recallum_doctor.py
   ```

   It must be a streamable HTTP server whose URL ends in `/mcp` or `/mcp/` and whose
   `bearer_token_env_var` names the intended environment variable.
3. Start a new Codex thread after installation so plugin skills and MCP tools are rediscovered.
4. Open `/hooks`, review the Recallum hooks, and trust them only if their plugin path is this
   installation.

## Setup — Claude Code

Claude Code uses **two** complementary MCP registrations after `install.sh --target claude`:

1. **Plugin-bundled** `.mcp.json` — `${user_config.mcp_url}` and
   `Bearer ${user_config.api_token}` (pluginSecrets / `/plugin configure`). Tools appear as
   `mcp__plugin_recallum-memory_recallum__*`. Exporting `RECALLUM_API_KEY` alone does **not**
   authenticate this path.
2. **Native user MCP** in `~/.claude.json` → `mcpServers.recallum` — real URL plus desktop-safe
   Bearer (literal when the installer stores a key). Tools appear as `mcp__recallum__*`. **Claude
   Desktop** often fails to put plugin-bundled HTTP MCP into the deferred ToolSearch catalog; the
   native entry is what Desktop sessions need.

Cursor uses a separate `mcp.json` under the server key `recallum_memory` so it does not collide with
Claude's `recallum` entry when both configs are present in the same package.

`mcp_url` is `required`, with no default: the endpoint must be your own Recallum server, so
enabling the plugin prompts for it rather than pointing at someone else's.

1. Confirm the plugin marketplace and installation:
   `claude plugin marketplace list --json` must contain `recallum-local` at this repository root,
   and `claude plugin list --json` must contain the id `recallum-memory@recallum-local`.
2. Confirm the native Desktop entry and plugin credential without opening credential-bearing JSON:

   ```bash
   python3 plugins/recallum-memory/scripts/recallum_doctor.py
   ```

   The doctor reports only redacted auth state, file permissions, and whether the plugin credential
   can resolve. Never pass the key with `--config api_token=...`. Only `mcp_url` is safe on the CLI.

   **With neither pluginSecrets nor a native Bearer, tool calls fail auth.** A healthy
   `claude mcp list` line is not evidence of working Desktop ToolSearch.
4. Session-level check (not nested shell):

   - **CLI:** ToolSearch / tool list includes `mcp__plugin_recallum-memory_recallum__*` and/or
     `mcp__recallum__*`.
   - **Desktop:** ToolSearch `+recallum` or `select:mcp__recallum__context` must return matches.
     Running `claude mcp list` from Bash **inside** a Desktop session uses a separate CLI process
     and is a **false green** if Desktop’s own deferred catalog lacks Recallum.
5. Fully quit Claude.app (Desktop) or restart the CLI session after install so hooks and MCP reload.
6. Verify the plugin manifest with `claude plugin validate <repo-root> --strict` and
   `claude plugin validate <repo-root>/plugins/recallum-memory --strict`.

## Setup — Cursor

Prefer the installer (marketplace + desktop-safe MCP config):

```bash
export RECALLUM_API_KEY=rcl_…
plugins/recallum-memory/scripts/install.sh --target cursor --url https://recallum.example.com/mcp/
```

Then install `recallum-memory` from marketplace `recallum-local` inside Cursor (Settings → Plugins
or `/plugins`). Fully quit and reopen Cursor. The installer writes `~/.cursor/mcp.json` with a
literal Bearer (mode 600) because Cursor desktop does not reliably expand shell env vars and plugin
Configure is often unavailable for user marketplaces. For one-off local CLI testing:

```bash
agent --plugin-dir /path/to/recallum-mcp/plugins/recallum-memory
```

Tools appear under Available Tools. Cursor's `sessionStart` hook returns context through top-level
`additional_context`, but delivery is best-effort. The always-applied rule and the
`recallum-memory` skill define the exact canonical-key fallback when that context is absent.

## Setup — Grok Build

Grok does **not** resolve Claude-style `${user_config.*}` placeholders in a plugin MCP config.
Register the MCP server natively in `~/.grok/config.toml` (the installer does this) so the URL and
`Authorization: Bearer ${RECALLUM_API_KEY}` form are real values Grok expands at connect time. That
native entry takes precedence over any broken plugin-bundled MCP definition with the same name.

1. Confirm the marketplace and plugin:
   `grok plugin marketplace list --json` must contain `recallum-local`, and
   `grok plugin list --json` must show `recallum-memory` enabled.
2. Inspect the MCP entry with the secret-safe, read-only doctor (never print expanded secrets from
   `grok mcp list --json`, which interpolates env vars for display):

   ```bash
   python3 plugins/recallum-memory/scripts/recallum_doctor.py
   ```

   `url` must end in `/mcp/`, and `authorization` must be exactly
   `Bearer ${RECALLUM_API_KEY}` (or the custom `--token-env-var` name), not a static key.
3. Confirm connectivity without printing the key:

   ```bash
   grok mcp doctor recallum
   ```

   Expect handshake OK and nine tools discovered.
4. Export `RECALLUM_API_KEY` in the environment that launches Grok, then start a **new** session.
5. Optional: validate the plugin with `grok plugin validate <repo-root>/plugins/recallum-memory`.

## Setup — Antigravity CLI

Antigravity CLI ships as `agy`. It performs no environment-variable expansion in its MCP config, so
the API key is written to disk in cleartext — read the whole section before running the installer.

1. Confirm `agy` is on `PATH` (`agy --version`).
2. Run the installer:

   ```bash
   export RECALLUM_API_KEY=rcl_YOUR_API_KEY
   plugins/recallum-memory/scripts/install.sh --target antigravity --url https://recallum.example.com/mcp/
   ```

   This calls `agy plugin install <dir>` (accepts a local directory or an **HTTPS** GitHub URL only
   — `git@…` and the `owner/repo` shorthand both fail) and writes the `recallum` server natively to
   `~/.gemini/config/mcp_config.json` at mode `0600`. `--target both` does not cover Antigravity CLI;
   use `--target antigravity` explicitly. `--remote` does not currently cover this target.
3. **Cleartext key warning:** the bearer token is written literally into
   `~/.gemini/config/mcp_config.json` — a `${RECALLUM_API_KEY}`-style placeholder will **not** be
   expanded by Antigravity. The installer's backup of the prior config also holds the key in
   cleartext. Treat both files as sensitive; never commit either one.
4. Confirm the registration with the read-only doctor:

   ```bash
   python3 plugins/recallum-memory/scripts/recallum_doctor.py
   ```

   It reports the `Antigravity CLI` client: server presence, `serverUrl`, the Authorization header
   (flagging any unexpanded `${...}` placeholder as wrong for this client), the config file's
   permission mode, and whether `agy plugin list` shows the plugin. If `agy` is not on `PATH`, that
   last sub-check is skipped, not failed.
5. Optional: `agy plugin validate plugins/recallum-memory` — expect `mcpServers : 1 processed` and
   `skills : 2 processed`. It also reports `hooks : 1 processed`, but that is validation acceptance
   only, not evidence the hook ever dispatches (see Diagnostics below).
6. Start a new Antigravity session so the plugin and MCP server are picked up.

Skills validate cleanly (`skills : 2 processed`), but that is validation acceptance only — it is
not evidence that skill-driven tool discovery works at runtime. Session-start hook parity is also
**unconfirmed**: `agy` gates every session behind interactive Google OAuth sign-in before any
session-start hook, hook dispatch, or MCP tool surface becomes reachable, so do not rely on a
hook-injected context digest for Antigravity CLI. The MCP tool-name prefix for Antigravity CLI is
also not yet determined — no prefix constant exists in the shared hook code.

## Shared Checks

1. Check only whether the token environment variable or Claude Code fallback is present. The
   read-only doctor reports set or unset and never reveals its value:

   ```bash
   python3 plugins/recallum-memory/scripts/recallum_doctor.py
   ```
2. Confirm the server is ready and that tool discovery exposes the Recallum tools — at least
   `context`, `recall`, `remember`, `list_memories`, and `forget` (current servers also expose
   `get_memory`, `remember_batch`, `update`, and `merge_memories`) — under the prefix for that
   client:

   | Client | Prefix |
   | --- | --- |
   | Codex | `mcp__recallum__` |
   | Claude Code (plugin) | `mcp__plugin_recallum-memory_recallum__` |
   | Claude Code (native / Desktop) | `mcp__recallum__` |
   | Grok Build | `recallum__` (via `search_tool` / `use_tool`) |
   | Cursor | Recallum MCP tools in Available Tools (no stable textual prefix) |
   | Antigravity CLI | **not yet determined** — no prefix constant exists; prefer skill-driven tool discovery |

   Claude Code namespaces a plugin-bundled server as `plugin:<plugin>:<server>` and rewrites every
   character outside `[A-Za-z0-9_-]` to `_` when building tool ids (long prefix). The installer also
   dual-writes a user MCP named `recallum` for Desktop ToolSearch (short prefix).
3. Verify the session-start hook contributes context in a new session.

## Cross-session Check

With the user's approval, store one harmless, uniquely worded sentinel as a project-scoped fact.
Start a new session, load project context, and verify the exact sentinel is returned. Remove the
sentinel afterward with `mcp__recallum__forget` if the user does not want to retain it.

## Optional: Session Context Digest

The session hook can inject a compact memory digest at session start without waiting for the model
to call any tool. It activates only when both `RECALLUM_MCP_URL` (the same URL configured for the
MCP server) and `RECALLUM_API_KEY` are exported in the environment that launches the client. The
fetch runs under a ~2.5 s budget and fails open: if either variable is missing or the server is
slow, unreachable, or returns anything unexpected, the hook emits the standard instruction-only
hint and the session continues unaffected. Configure it only when the user asks for it, and never
echo the key while doing so.

## Diagnostics

- Missing tools after install: start a new session, then inspect plugin installation and MCP
  discovery.
- **Desktop ToolSearch 0 results for recallum (CLI works):** plugin hooks can fire while plugin MCP
  tools never enter Desktop’s deferred catalog. Confirm `~/.claude.json` has `mcpServers.recallum`,
  re-run `install.sh --target claude --force-mcp`, fully quit Claude.app, and re-check with
  ToolSearch `+recallum` — not with nested `claude mcp list`.
- **Cursor/cache leak:** never inspect or print Cursor `mcp.json` or cached `.mcp.json` with ad-hoc
  JSON/TOML recipes. The Cursor cache can load Claude-only `${user_config.*}` entries and can expose
  a literal bearer; run `python3 plugins/recallum-memory/scripts/recallum_doctor.py`
  and treat any cache-leak or permission issue as a failure.
- Authentication failure on Codex: verify the named environment variable is present in the
  environment that launches Codex and that the key is active; do not request the value in chat.
- Authentication failure on Claude Code: re-run install (pluginSecrets + native Bearer) or
  `/plugin configure recallum-memory@recallum-local`. Do not ask for the value in chat and do not
  read it back.
- Authentication failure on Grok Build: verify `RECALLUM_API_KEY` is exported for the Grok process
  and that `~/.grok/config.toml` has `Authorization = "Bearer ${RECALLUM_API_KEY}"` (unexpanded).
  A plugin-only MCP entry showing `url = "${user_config.mcp_url}"` is broken on Grok — re-run
  `scripts/install.sh --target grok` (or `--force-mcp` if a stale definition exists).
- Connection failure: verify the URL and service readiness independently, then retry discovery.
- Hook absent or blocked (Codex): use `/hooks` to inspect the path and trust state; never bypass the
  trust review.
- Hook not firing (Claude Code): confirm the plugin is enabled, then check that `python3` or
  `python` is on the PATH of the process that launched Claude Code. The hook fails open, so a
  missing interpreter is silent.
- Hook not firing (Grok Build): confirm `grok plugin list` shows `recallum-memory` enabled and
  trusted, and that `python3` is on PATH.
- Hook not firing (Antigravity CLI): expected. `agy plugin validate` reporting `hooks : 1 processed`
  is validation acceptance only, not dispatch evidence — `agy` gates every session behind
  interactive Google OAuth sign-in before any session-start hook is reachable, so hook parity is
  unconfirmed. Use skill-driven tool discovery instead of relying on a hook-injected context digest.
