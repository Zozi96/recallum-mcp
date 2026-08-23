# QA report — S003

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- Full suite: **176 passed, 90 subtests** (main baseline 134). Antigravity/agy subset: 42 passed, 19 subtests. `git status --short` shows no tracked-file drift.
- **Plugin-name match verified against the real binary.** `agy plugin list --json` returns `imports[].name` as `"recallum-memory"` — the plugin name, not the `recallum` MCP server name. Production code (`_antigravity_plugin_present`, recallum_doctor.py:590) matches `item.get("name") == "recallum-memory"`, and the fixture `_write_agy_cli` (test_plugin.py:2716) emits the same. Code, fixture and real binary all agree, so there is no false-negative from a name mismatch.
- **D2's three states are genuinely distinct** (recallum_doctor.py:567-600): present (JSON, entry found, `mcpServers` in components) / not present (JSON entry missing, or non-JSON zero-exit text matching `AGY_NO_PLUGINS_PATTERN`) / cannot tell (`agy` absent, `_run_text` None, or non-JSON text not matching the pattern). The malformed-JSON and nonzero-exit tests (L3224, L3237) assert `plugin_present` absent and no `Traceback`, so a crash can never surface as a clean "not present".
- **D1 is Antigravity-specific.** The placeholder check lives only in `_antigravity` (recallum_doctor.py:621-635), inside the Antigravity config path, not in shared `_auth_problem`. The four sibling clients call only `_auth_problem`, unchanged, so their env-var expansion is unaffected.
- `_safe_server` / `_record_permission` gained only optional kwargs (`url_key="url"`, `client=None`) whose defaults reproduce prior behavior byte-for-byte; all four sibling-client suites pass.
- PATH isolation holds: `_run_doctor` replaces PATH entirely (`home/bin:/usr/bin:/bin`), and every agy-consulting test asserts `FAKE_AGY_SENTINEL_v1`, guarding against silent fallthrough to the real `/home/zozi/.local/bin/agy`.
- The umask test (L3045) chmods after write and asserts `file_mode == "0644"` under `os.umask(0o077)` — it genuinely proves the bug is not umask-maskable.
- Redaction assertions are non-vacuous: the token and its suffix are asserted absent across text and JSON, healthy and unhealthy, including the `0644`-plus-placeholder combination, with no traceback in any case.

## Evidence

- Leader-verified independently against the real `agy` v1.1.19: no plugins → `No imported plugins.` (plain text, exit 0); after install → JSON with `imports[].name = "recallum-memory"`, `components: ["skills","mcpServers"]`.

## Gaps

- None blocking.
