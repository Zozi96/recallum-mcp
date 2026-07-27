---
name: recallum-setup
description: Set up or diagnose the Recallum plugin and remote MCP connection for Codex when the user explicitly asks to install, configure, verify, troubleshoot, or test Recallum.
---

# Recallum Setup

Diagnose without exposing credentials. Never print, echo, interpolate, or store an API key value.

## Setup

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
3. Check only whether that environment variable is present. Report set or unset; never reveal its
   value.
4. Start a new Codex thread after installation or configuration so plugin skills and MCP tools are
   rediscovered.
5. Confirm the server is ready and that tool discovery exposes exactly:
   `mcp__recallum__remember`, `mcp__recallum__recall`, `mcp__recallum__context`,
   `mcp__recallum__list_memories`, and `mcp__recallum__forget`.
6. Open `/hooks`, review the Recallum hooks, and trust them only if their plugin path is this
   installation. Verify the session-start hook contributes context in a new thread.

Prefer the bundled `scripts/install-codex.sh` for configuration. It validates the endpoint,
registers the repo marketplace, installs the plugin, and configures the bearer-token environment
variable reference without storing the token.

## Cross-session Check

With the user's approval, store one harmless, uniquely worded sentinel as a project-scoped fact.
Start a new thread, load project context, and verify the exact sentinel is returned. Remove the
sentinel afterward with `mcp__recallum__forget` if the user does not want to retain it.

## Diagnostics

- Missing tools after install: start a new thread, then inspect plugin installation and MCP
  discovery.
- Authentication failure: verify the named environment variable is present in the environment
  that launches Codex and that the key is active; do not request the value in chat.
- Connection failure: verify the URL and service readiness independently, then retry discovery.
- Hook absent or blocked: use `/hooks` to inspect the path and trust state; never bypass the trust
  review.
