---
name: recallum-setup
description: Set up or diagnose the Recallum plugin and remote MCP connection for Codex or Claude Code when the user explicitly asks to install, configure, verify, troubleshoot, or test Recallum.
---

# Recallum Setup

Diagnose without exposing credentials. Never print, echo, interpolate, or store an API key value.

Prefer the bundled `scripts/install.sh` for configuration. It validates the endpoint, registers the
repo marketplace, installs the plugin, and configures the bearer-token environment variable
reference without storing the token. Use `--target codex`, `--target claude`, `--target both`, or
the default `--target auto` (every detected CLI). Run it with `--dry-run` first to see the planned
actions.

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
`Authorization` header are filled from the `userConfig` values `mcp_url` and `api_token`.

1. Confirm the plugin marketplace and installation:
   `claude plugin marketplace list --json` must contain `recallum-local` at this repository root,
   and `claude plugin list --json` must contain the id `recallum-memory@recallum-local`.
2. Set or check the configuration with `/plugin configure recallum-memory@recallum-local`.
   `api_token` is declared `sensitive`, so Claude Code masks it. Never pass the key with
   `--config api_token=...`: that puts the credential in argv, shell history, and the process list.
   Only `mcp_url` is safe to pass that way, and `scripts/install.sh` does exactly that.
3. Confirm the server is reachable:

   ```bash
   claude mcp list | grep recallum
   ```

   It appears as `plugin:recallum-memory:recallum`. A missing or unset `userConfig` value shows up
   as a connection failure, and `claude plugin install` reports `userConfig option not yet set`.
4. Restart the Claude Code session after installation or reconfiguration so the plugin, its hooks,
   and the MCP tools load.
5. Verify the plugin manifest with `claude plugin validate <repo-root> --strict` and
   `claude plugin validate <repo-root>/plugins/recallum-memory --strict`.

## Shared Checks

1. On Codex, check only whether the token environment variable is present. Report set or unset;
   never reveal its value. On Claude Code, report only whether `api_token` is configured.
2. Confirm the server is ready and that tool discovery exposes exactly five tools — `context`,
   `recall`, `remember`, `list_memories`, and `forget` — under the prefix for that client:

   | Client | Prefix |
   | --- | --- |
   | Codex | `mcp__recallum__` |
   | Claude Code | `mcp__plugin_recallum-memory_recallum__` |

   Claude Code namespaces a plugin-bundled server as `plugin:<plugin>:<server>` and rewrites every
   character outside `[A-Za-z0-9_-]` to `_` when building tool ids, which is where the longer
   prefix comes from.
3. Verify the session-start hook contributes context in a new session.

## Cross-session Check

With the user's approval, store one harmless, uniquely worded sentinel as a project-scoped fact.
Start a new session, load project context, and verify the exact sentinel is returned. Remove the
sentinel afterward with `mcp__recallum__forget` if the user does not want to retain it.

## Diagnostics

- Missing tools after install: start a new session, then inspect plugin installation and MCP
  discovery.
- Authentication failure on Codex: verify the named environment variable is present in the
  environment that launches Codex and that the key is active; do not request the value in chat.
- Authentication failure on Claude Code: re-run `/plugin configure recallum-memory@recallum-local`
  and re-enter the key. Do not ask for the value in chat and do not read it back.
- Connection failure: verify the URL and service readiness independently, then retry discovery.
- Hook absent or blocked (Codex): use `/hooks` to inspect the path and trust state; never bypass the
  trust review.
- Hook not firing (Claude Code): confirm the plugin is enabled, then check that `python3` or
  `python` is on the PATH of the process that launched Claude Code. The hook fails open, so a
  missing interpreter is silent.
