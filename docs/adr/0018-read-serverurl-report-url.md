# ADR 0018: Read `serverUrl`, report `url`

## Status
Accepted

## Context
Antigravity's `~/.gemini/config/mcp_config.json` keys a remote server's endpoint `serverUrl`. The other four clients key it `url`. This is not a stylistic difference: S002 verified that Antigravity rejects a `type`/`url` entry outright (`MCP server "recallum" must have either command or serverUrl`), so the installer must write `serverUrl` and the doctor must read it.

S003 threaded this through `_safe_server(server, url_key="serverUrl")`. The helper's *output* key stays `"url"` regardless of which input key it read, so `report["clients"]["Antigravity CLI"]["native_mcp"]["url"]` has the same shape as every other client's.

## Decision
Keep the split: per-client input key, uniform report key. Do not normalize `serverUrl` into `url` at write time, and do not surface `serverUrl` as the report key for Antigravity.

## Alternatives considered
- Have `_safe_server` accept both keys and prefer whichever is present: rejected; it would silently accept a `url` entry for Antigravity that the client itself rejects, turning a config error into a clean doctor report.
- Report under the on-disk key (`serverUrl` for Antigravity): rejected; `--json` consumers and `_render_text` would need per-client knowledge to find the endpoint, and the redaction contract in `_safe_url` is defined on one output shape.

## Consequences
The doctor's report is a normalized view, not a literal mirror of the file — an operator reading `native_mcp.url` for Antigravity is looking at a value stored under `serverUrl`. The problem strings compensate by naming the real key ("Antigravity CLI serverUrl is missing"). A future client with a third spelling adds one more `url_key` argument, within the budget ADR 0017 sets.
