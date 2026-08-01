---
name: recallum-setup
description: Set up or diagnose the Recallum plugin and remote MCP connection for Codex, Claude Code, or Grok Build when the user explicitly asks to install, configure, verify, troubleshoot, or test Recallum.
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
`--no-store-api-key` to skip persistence. Targets: `--target codex`, `claude`, `grok`, `both`, or
default `auto`. Run with `--dry-run` first to see the planned actions.

## Setup — Codex

1. Confirm the plugin marketplace and installation:
   `codex plugin marketplace list --json` must contain `recallum-local` at this repository root,
   and `codex plugin list` must show `recallum-memory`.
2. Inspect only safe MCP fields; discard static headers because an older definition may contain a
   credential:

   ```bash
   codex mcp get recallum --json | python3 -c '
   import json, sys
   data = json.load(sys.stdin)
   transport = data.get("transport", {})
   safe = {
       "name": data.get("name"),
       "type": transport.get("type"),
       "url": transport.get("url"),
       "bearer_token_env_var": transport.get("bearer_token_env_var"),
   }
   print(json.dumps(safe, indent=2))
   '
   ```

   It must be a streamable HTTP server whose URL ends in `/mcp` or `/mcp/` and whose
   `bearer_token_env_var` names the intended environment variable.
3. Start a new Codex thread after installation so plugin skills and MCP tools are rediscovered.
4. Open `/hooks`, review the Recallum hooks, and trust them only if their plugin path is this
   installation.

## Setup — Claude Code

Claude Code does not use a separate MCP registration. The plugin ships `.mcp.json`, whose `url` and
`Authorization` header are filled from `userConfig`. Authentication uses
`${RECALLUM_API_KEY:-${user_config.api_token}}`: the environment variable wins, with the masked
plugin option as fallback. Claude Code substitutes `${user_config.*}` before expanding environment
variables, which is what makes the nested default resolve — a generic nested `${A:-${B}}` in an
`.mcp.json` does not, so do not copy this shape into a non-plugin config.

`mcp_url` is `required`, with no default: the endpoint must be your own Recallum server, so
enabling the plugin prompts for it rather than pointing at someone else's.

1. Confirm the plugin marketplace and installation:
   `claude plugin marketplace list --json` must contain `recallum-local` at this repository root,
   and `claude plugin list --json` must contain the id `recallum-memory@recallum-local`.
2. Check whether a credential can resolve: `RECALLUM_API_KEY` in the process environment, or
   `pluginSecrets["recallum-memory@recallum-local"].api_token` in `~/.claude/.credentials.json`
   (written by `install.sh` or `/plugin configure`). Never pass the key with
   `--config api_token=...`: that puts the credential in argv, shell history, and the process list.
   Only `mcp_url` is safe on the CLI, and `scripts/install.sh` does exactly that.

   **With neither set, the failure is silent until the first tool call.** The server's bearer
   middleware only guards tool invocation, so the MCP connection still reports healthy and
   `claude mcp list` shows a connected server; the header is just the literal unexpanded
   placeholder. Diagnose it by calling a tool — an unauthenticated call returns
   `authentication required: send 'Authorization: Bearer <api-key>'`, and a wrong or revoked key
   returns `invalid or revoked API key`. A healthy connection is not evidence of working auth.
3. Confirm the server is reachable:

   ```bash
   claude mcp list | grep recallum
   ```

   It appears as `plugin:recallum-memory:recallum`. A missing environment variable with no
   configured fallback shows up as a connection failure. The installer may still call the fallback
   unset when the environment variable is present; that warning does not block environment
   expansion.
4. Restart the Claude Code session after installation or reconfiguration so the plugin, its hooks,
   and the MCP tools load.
5. Verify the plugin manifest with `claude plugin validate <repo-root> --strict` and
   `claude plugin validate <repo-root>/plugins/recallum-memory --strict`.

## Setup — Grok Build

Grok does **not** resolve Claude-style `${user_config.*}` placeholders in a plugin `.mcp.json`.
Register the MCP server natively in `~/.grok/config.toml` (the installer does this) so the URL and
`Authorization: Bearer ${RECALLUM_API_KEY}` form are real values Grok expands at connect time. That
native entry takes precedence over any broken plugin-bundled MCP definition with the same name.

1. Confirm the marketplace and plugin:
   `grok plugin marketplace list --json` must contain `recallum-local`, and
   `grok plugin list --json` must show `recallum-memory` enabled.
2. Inspect only safe MCP fields from config (never print expanded secrets from
   `grok mcp list --json`, which interpolates env vars for display):

   ```bash
   python3 - <<'PY'
   from pathlib import Path
   import tomllib
   cfg = tomllib.loads(Path.home().joinpath(".grok/config.toml").read_text())
   server = cfg.get("mcp_servers", {}).get("recallum", {})
   headers = server.get("headers") or {}
   print({
       "url": server.get("url"),
       "enabled": server.get("enabled", True),
       "authorization": headers.get("Authorization"),
   })
   PY
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

## Shared Checks

1. Check only whether the token environment variable or Claude Code fallback is present. Report set
   or unset; never reveal its value.
2. Confirm the server is ready and that tool discovery exposes the Recallum tools — at least
   `context`, `recall`, `remember`, `list_memories`, and `forget` (current servers also expose
   `get_memory`, `remember_batch`, `update`, and `merge_memories`) — under the prefix for that
   client:

   | Client | Prefix |
   | --- | --- |
   | Codex | `mcp__recallum__` |
   | Claude Code | `mcp__plugin_recallum-memory_recallum__` |
   | Grok Build | `recallum__` (via `search_tool` / `use_tool`) |

   Claude Code namespaces a plugin-bundled server as `plugin:<plugin>:<server>` and rewrites every
   character outside `[A-Za-z0-9_-]` to `_` when building tool ids, which is where the longer
   prefix comes from.
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
- Authentication failure on Codex: verify the named environment variable is present in the
  environment that launches Codex and that the key is active; do not request the value in chat.
- Authentication failure on Claude Code: verify `RECALLUM_API_KEY` was exported before Claude
  started, or re-run `/plugin configure recallum-memory@recallum-local`. Do not ask for the value
  in chat and do not read it back.
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
