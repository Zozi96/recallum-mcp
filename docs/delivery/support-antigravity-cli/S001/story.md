# S001 — Add a validated MCP config to the Recallum plugin bundle

## Actor
Antigravity CLI (`agy`) validating and installing the `recallum-memory` plugin bundle; the Antigravity CLI user who runs `agy plugin install`.

## Objective and motivation
The plugin bundle at `plugins/recallum-memory/` (already used by Claude Code, Grok Build, Cursor) has no `mcp_config.json`, so `agy plugin validate` reports `mcpServers` as "not found" and `agy plugin install` cannot wire the Recallum MCP server for Antigravity. Add a bundle-level `mcp_config.json` in the `serverUrl` shape Antigravity requires (verified constraint 2), so the plugin carries the same self-contained tool registration Claude Code and Grok Build already get, and record whether Antigravity actually activates it at runtime (OQ4) — this determines whether native registration (S002) is redundant belt-and-braces or the only working path.

## In scope
- A `mcp_config.json` at the plugin bundle root (`plugins/recallum-memory/mcp_config.json`) using `{"mcpServers":{"recallum":{"serverUrl":"…/mcp/","headers":{"Authorization":"Bearer …"}}}}`, matching the schema `agy plugin validate` accepts per constraint 2.
- Keeping `plugin.json` valid under `agy plugin validate` with no regressions to existing fields.
- An isolated-HOME probe (mirroring the one that produced constraint 3) that installs the bundle via `agy plugin install` and observes whether the `recallum` MCP server becomes reachable/listed to the running CLI without any native `~/.gemini/config/mcp_config.json` entry present — this is the OQ4 runtime check.
- Recording the OQ4 probe's outcome (honoured / not honoured / inconclusive) and its evidence (command output, logs) as part of this story's deliverable.

## Out of scope
- Any change to `install.sh`, `recallum_doctor.py`, or `recallum_hook.py` (S002/S003/S004 respectively).
- Writing or merging the native `~/.gemini/config/mcp_config.json` file (S002).
- Resolving OQ1-OQ3 (hooks); this story only touches OQ4.
- Choosing or storing a real secret at install time — this story's bundle config may use a placeholder/templated header; literal secret injection into a live `~/.gemini` install is S002's concern.

## Dependencies
None required to land this story. S002 (native MCP registration) does not require this story to land first — the native write in S002 is a separate file the installer controls directly, independent of the bundle's `mcp_config.json`. However, this story's OQ4 finding directly determines whether S002's native write is belt-and-braces or the only working MCP path; both stories' outcomes should be read together before the pair is considered "done" from a product standpoint (see the corresponding note in S002's Dependencies).

## Acceptance criteria
- `agy plugin validate plugins/recallum-memory` reports `mcpServers` as present/processed (not "not found"), with `skills: 2 processed` still reported unchanged.
- The written `mcp_config.json` round-trips through `agy plugin validate` without the "must have either command or serverUrl" error.
- The OQ4 probe produces one of exactly three recorded outcomes with evidence: (a) "honoured" — a fresh, isolated-HOME `agy plugin install` of the bundle alone (no native config present) results in the `recallum` server appearing among the running CLI's active MCP servers; (b) "not honoured" — same setup, the server does not appear; (c) "inconclusive" — permitted only after at least one genuine interactive-mode attempt (the same evidence bar S004 requires for its own gap outcome, since `agy plugin install` followed by tool-availability inspection is not meaningfully checkable in headless/`-p` mode), with the transcript of what was tried and what was observed, plus the specific technical blocker that prevented a "honoured"/"not honoured" determination (e.g., no way to enumerate the running CLI's active MCP servers, a crash, a permission error unrelated to OQ4 itself). A probe that only attempted headless/non-interactive invocation does not qualify for "inconclusive".
- `plugin.json` continues to validate with no new errors introduced by adding `mcp_config.json`.
- No secret value is committed to the repository; any header value in the bundle file uses a non-secret placeholder or the same interpolation scheme already accepted by `agy plugin validate`.
