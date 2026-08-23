# ADR 0022: Keep the hook's client roster closed to Antigravity

## Status
Accepted

## Context
`hooks/recallum_hook.py` identifies its host from client root env vars and emits client-specific tool spellings. It knows four clients — `CURSOR_TOOL_PREFIX` handling plus `CODEX_TOOL_PREFIX`, `CLAUDE_TOOL_PREFIX`, `CLAUDE_NATIVE_TOOL_PREFIX`, `GROK_TOOL_PREFIX` (L39-42) — dispatched in `_tool()` (L174-189), `_lookup_hint()` (L215-231), and `_emit()`.

Antigravity is the fifth client the theme adds, and the obvious symmetry is a fifth branch. S004 established that no `SessionStart` dispatch happens under `agy` at all (OQ1). A branch or an `ANTIGRAVITY_TOOL_PREFIX` constant could therefore never be entered or matched, and its tool spelling could never be checked against anything — it would be dead code whose only effect is to make the file *look* like it supports five clients. The theme never touched `recallum_hook.py`; stage 7 verified that with an empty `git log main..HEAD` on the file.

`test_recallum_hook_has_no_antigravity_branch_or_prefix_constant` (S004, commit `fc09e57`) pins this by asserting `"ANTIGRAVITY"` and `"antigravity"` are absent from the hook's source. It is the negative half of an invariant whose positive half already existed: `test_hook_and_tests_agree_on_all_tool_prefixes` (L1092) execs the four prefix assignments out of the source and compares them to the suite's own constants. Together they say the roster is closed at four and names which four.

## Decision
Keep `recallum_hook.py` free of any Antigravity branch or prefix constant, and keep the absence pinned by test. Re-adding one requires runtime dispatch evidence superseding `docs/delivery/support-antigravity-cli/S004/oq123-evidence.md` — not a symmetry argument.

Do **not** generalise "pin an absence by test" into a repo pattern. This is the only absence pin in the suite, it exists because a specific wrong fix is attractive here, and ADR 0017 already declines to generalise from a comparable n=1.

## Alternatives considered
- Add the fifth branch for symmetry: rejected; this is precisely the failure the theme spent effort avoiding — a future contributor "fixing" a gap that a prefix constant cannot fix, then a reviewer reading five branches as five working clients.
- Record the decision in a comment in `recallum_hook.py` instead of a test: rejected because it would violate the theme's own constraint of not touching the file, and because a comment does not fail when someone adds the branch anyway.
- Pin the absence only in the ADR, with no test: rejected; the ADR is not in the contributor's edit path and the test is.
- Write the ADR about absence-pinning as a general technique: rejected, see the Decision. The durable content here is which roster is closed and why, not the assertion style.

## Consequences
The assertion is a substring match over the whole source file. Any legitimate future mention of the word — a docstring naming Antigravity as a client the hook deliberately does not serve — will fail the test. That is a false positive by construction, and the correct response is to change this ADR and the test together, not to work around the string.

A real hazard is carried forward. `hooks.json` resolves its plugin root as `${PLUGIN_ROOT:-${GROK_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}}`, and `_tool()` treats a set `PLUGIN_ROOT` with no `GROK_PLUGIN_ROOT` as **Codex** (L178-179). So if agy ever begins dispatching `SessionStart` and sets `PLUGIN_ROOT`, the hook will not fail closed and will not fall through to the all-spellings default — it will silently identify the session as Codex and emit `mcp__recallum__`. Whether that spelling is correct under agy is unknown and untestable today, since no dispatch exists to observe. If agy sets none of the three roots, the shell guard `[ -n "$p" ]` makes the hook exit 0 without running, which is the safe outcome. Neither path is covered by a test, because neither is reachable.
