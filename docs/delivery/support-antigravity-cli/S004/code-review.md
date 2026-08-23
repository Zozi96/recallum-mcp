# Code review — S004

verdict: pass
bounce_to: none
attempt: 1
senior_implementer: false

## Reasons

- **The Gap branch is earned.** The story's bar is "no dispatch after a genuine interactive attempt". The pty run initialised the TUI and created a resumable conversation, so `SessionStart`'s trigger point was reached, and `cli.log` shows no hook entry *and* no parse error — the hook subsystem never engaged, rather than engaging and failing late. A human-driven session could differ only if `agy` defers hook dispatch past session creation; no evidence supports that, and the log's silence argues against it.
- **Pinning the absence is right, not ossification.** With zero dispatch, any `ANTIGRAVITY_TOOL_PREFIX` or detection branch would be dead code that fakes parity — precisely the failure this theme guarded against. The test is a deliberate tripwire, trivially deleted once new dispatch evidence supersedes `oq123-evidence.md`, and its comment says so.
- **The constraint-5 test asserts observed reality only**: `assertNotIn("cannot unmarshal")` plus `hooks : 1 processed` for both schemas, at the validate layer it actually exercises. It encodes no guess about where a runtime error might live; the evidence file carries that caveat, not the test.
- **The inert `hooks.json` should be kept**, and S001's reasoning carries. The bundle-root `hooks.json` is Antigravity's location; `agy` never dispatches it, so there is zero session-start cost. Claude Code and Grok read `hooks/hooks.json` — the array-plus-matcher form, untouched — so there is no shadowing and no double dispatch. If `agy` later fixes dispatch, the command execs `recallum_hook.py` and no-ops safely on unknown env, making the file the seam rather than a shadow. The misleading `hooks : 1 processed` is agy's own output; the hazard is neutralised in `docs/clients.md` and the evidence file.
- **No regression.** Both commits touch only the new `plugins/recallum-memory/hooks.json`, appended tests, and docs. `recallum_hook.py` and the existing Codex/Claude Code/Grok Build/Cursor hook tests are unmodified.

## Evidence

- Reviewer ran the full suite: 179 passed, 92 subtests (main baseline 134).
- OQ1 resolved against real `agy` v1.1.19 in an authenticated profile; earlier OAuth walls were an artifact of `HOME=$(mktemp -d)`.
- Theme constraint 5 disproved by leader probe: `agy` accepts both the Claude array-of-groups and the Antigravity single-object schema at `validate` and at `install`.

## Gaps

- Non-blocking maintenance nit: `test_skills_and_mcp_servers_unaffected_by_hooks_json_presence` asserts the literal `"2 processed"` for skills (test_plugin.py ~L1430) and will need updating when a third skill lands.
- Two of the three tests skip without a real `agy` binary, so CI without `agy` pins only the absence test. Acceptable, worth knowing.
