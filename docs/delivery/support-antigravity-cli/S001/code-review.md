# Code review — S001

verdict: pass
bounce_to: none
attempt: 1
senior_implementer: false

## Reasons

- **Config correct**: `plugins/recallum-memory/mcp_config.json` uses `serverUrl` (no `type`/`url`/`command`), HTTPS with the exact `/mcp/` path, and a placeholder `Bearer <token>` only — no credential committed.
- **Ruling on shipping a runtime-inert bundle config: KEEP IT.** The misleading `✔ mcpServers : 1 processed` is emitted by `agy`, not by this repo; deleting the file would only regress validation to "skipped (not found)" without changing agy's indicator. The hazard is neutralised where this repo controls it: `oq4-evidence.md` records NOT HONOURED, S005 (`8f31441`) strips runtime claims from the docs, and no test or document asserts that the bundle wires MCP. S002's native write is documented as the only working path. Keeping the file is also forward-compatible if `agy` later propagates bundle configs.
- **No test claims runtime availability.** All 8 assert file shape, validator behavior, or install-time file copy. `test_agy_plugin_install_copies_mcp_config_into_isolated_home` (test_plugin.py:1374) checks file placement and never calls `agy mcp list`. 8 passed plus 5 subtests with `agy` present, so the 3 gated tests actually ran.
- **Legacy files untouched**: `git diff 3a7bb14^..HEAD` on `mcp.json` and `.mcp.json` is empty. The distinct server keys — `recallum_memory` versus `recallum` — are preserved and regression-guarded at test_plugin.py:1295.
- **Pyright `list[str | None]`**: confirmed a narrowing limitation, not a bug. `@skipUnless(AGY, ...)` guarantees non-None at runtime but cannot narrow the module global. Optional cleanup: `assert AGY is not None` at each guarded test head.

## Evidence

- OQ4 resolved against the real `agy` v1.1.19 in an authenticated profile: the plugin registers and its `mcpServers` component is recognised, but `agy mcp list` and the model's own view both show only `codegraph`. Full record in `S001/oq4-evidence.md`.

## Gaps

- **Non-blocking, for the analyst**: `story.md` AC3(b) literally requires an isolated-HOME probe, but the evidence used the authenticated real profile — isolation itself was what manufactured the OAuth wall. The deviation is documented and materially equivalent: no native `recallum` entry existed, and the config was snapshot-diffed clean afterwards. AC3 should be annotated to match how the question was actually answerable.
- Historical only: commit `3a7bb14`'s message says "OQ4 remains BLOCKED". Superseded by `0eee6ad`.
