# QA report — S004

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **Exactly one fork outcome is recorded.** `oq123-evidence.md` states the Gap branch, evidenced, with OQ2 and OQ3 moot. No Parity claim appears anywhere.
- `hooks.json` uses the required Antigravity single-object schema and validates under `agy plugin validate`.
- **No `ANTIGRAVITY_TOOL_PREFIX` was added**, correctly: with no hook process there is nothing to detect and no prefix to match. `test_recallum_hook_has_no_antigravity_branch_or_prefix_constant` (L1504) pins that absence, which satisfies the story's "if added, assert its value" clause vacuously and deliberately.
- **`AntigravityHookGapTests` (L1408-1514) asserts only what was observed**: that skills and mcpServers report identically with and without `hooks.json`; that validate and install accept both schemas (observed reality, with no guess about where a `cannot unmarshal` error might live); and the static absence of an Antigravity branch. No test asserts hook dispatch, stdin content, or runtime injection.
- **The non-vacuity guard holds.** `_report_line`'s `assert match is not None` (L1436) fails loudly when either regex does not match, so two absent lines cannot compare equal and pass silently.
- No fourth validation-versus-runtime confusion found. This theme was bitten by that three times; the hunt came back clean here.

## Evidence

- Full suite 179 passed, 92 subtests (main baseline 134); ruff clean.
- OQ1 resolved against real `agy` v1.1.19 in an authenticated profile: no dispatch in print mode, and none in a pty-driven interactive session where a resumable conversation was created. `cli.log` shows no hook entry and no parse error.
- CI degradation measured: 40 passed, 5 explicitly skipped without `agy`.

## Gaps

- None blocking.
