# QA report — S001

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **AC1, AC2, AC4, AC5 met.** `AntigravityMcpConfigTests` (test_plugin.py L1258-1406) covers the `serverUrl` shape, the endpoint rule, legacy files untouched, `plugin.json` unchanged, `agy plugin validate` reporting skills and mcpServers with no "must have either command or serverUrl" error, legacy-shape rejection, and install copying the file into an isolated HOME. All skip cleanly without `agy`.
- **AC3 met.** `oq4-evidence.md` records the outcome "not honoured" with a reproducible transcript: `agy plugin install` reports `mcpServers : 1 processed`, but `agy mcp list` and the model's own view show only `codegraph`.
- **The AC3(b) deviation is accepted.** The criterion literally wants an isolated-HOME probe, but isolation itself manufactures an OAuth wall unrelated to OQ4. No native `recallum` entry existed before the probe and the native config was snapshot-diffed clean afterwards, so the authenticated-profile run is materially equivalent to "no native config present". Stage 5 ruled the same way.
- **No test asserts unobserved runtime behavior** — file shape and validator output only.

## Evidence

- Full suite 179 passed, 92 subtests (main baseline 134); ruff clean.
- CI degradation measured by the leader: with `HOME` redirected and `PATH=/usr/bin:/bin`, the Antigravity-scoped subset is **40 passed, 5 skipped**, each skip carrying "agy binary not present on PATH or ~/.local/bin". With `agy` present: 45 passed. No silent passes.

## Gaps

- None blocking.
