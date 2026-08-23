# S001 — OQ4 evidence

Status: **RESOLVED — NOT HONOURED.**

## The question

Does a plugin-carried `mcp_config.json` get honoured at runtime? This decides whether the
native MCP registration in S002 is belt-and-braces or the only working path.

## Why earlier attempts failed, and what was wrong with them

Every earlier probe used `HOME=$(mktemp -d)` to avoid touching the developer's real
configuration. That creates a **virgin, unauthenticated profile**, so `agy` presented a Google
OAuth sign-in gate before any session or MCP surface was reachable. That gate was reported
three times as an environmental blocker requiring a human.

It was an artifact of the isolation choice, not a property of `agy`. The real profile at
`~/.gemini/` holds `antigravity-cli/antigravity-oauth-token` and answers `agy -p` with exit 0
and no prompt. The experiment was runnable all along.

## Method

Run against the authenticated profile, fully reversible, with no real credential involved —
the bundle carries only the placeholder `Bearer <token>`, and `agy plugin install` never writes
`~/.gemini/config/mcp_config.json` (independently confirmed).

The native config was snapshotted before and diffed after; the plugin was uninstalled afterwards.

## Result

```
1. baseline, no plugin installed
   $ agy mcp list
   NAME       TYPE   STATUS   COMMAND/URL
   codegraph  stdio  enabled  codegraph serve --mcp

2. install the bundle
   $ agy plugin install plugins/recallum-memory
   ✔ skills      : 2 processed
   ✔ mcpServers  : 1 processed

3. the question
   $ agy mcp list
   NAME       TYPE   STATUS   COMMAND/URL
   codegraph  stdio  enabled  codegraph serve --mcp        ← recallum absent

4. independent confirmation, via the model's own view
   $ agy -p "List the names of the MCP servers you currently have tools from."
   codegraph

5. the plugin IS registered, with the component recognised
   $ agy plugin list --json
   [('recallum-memory', ['skills', 'mcpServers', 'hooks'])]
```

## Conclusion

`agy` registers the plugin and recognises its `mcpServers` component at install time, but the
bundle-carried server **does not reach the runtime MCP server list**. `mcpServers : 1 processed`
is install-time acceptance, not runtime propagation — the same validation-versus-runtime
distinction that bit this theme twice elsewhere.

**Consequence for the theme.** The brief's decided model was "plugin bundle + native MCP", with
the native write as redundancy in case the plugin failed. That is backwards. The bundle supplies
the skills; the native `~/.gemini/config/mcp_config.json` write in S002 is **the only path that
makes the server available**. S002 is load-bearing, and ADR 0019's provisional reading is now
directly proven.

## Environment restored

Plugin uninstalled; `~/.gemini/config/mcp_config.json` diffed identical to the pre-experiment
snapshot; temporary files removed.
