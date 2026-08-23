# ADR 0023: Share the `agy plugin validate` test helpers

## Status
Accepted

## Context
S001 and S004 each needed to shell out to `agy plugin validate` and never saw each other's code. The result was three inline copies of the same seven-line `subprocess.run([AGY, "plugin", "validate", ...], cwd=REPO_ROOT, text=True, capture_output=True, check=False)` plus `result.stdout + result.stderr` in `AntigravityMcpConfigTests`, and a fourth copy extracted as `AntigravityHookGapTests._validate`. S004's copy discards `returncode`, which is exactly what two of S001's call sites assert on — so S001 could not have reused it as written even had it existed first.

The two stories also diverged on how to assert against the output, and the batch itself already ruled on which form is right. S004's stage 6 (commit `4ef08bc`, "assert the invariant, not the skill count") replaced a hard-coded skill count with `_report_line(output, section)`, an anchored `section\s*:\s*\d+ processed` match, on the grounds that the count changes whenever a skill is added. S001 still carried the older form: `assertIn("2 processed", output)` — which is not anchored to a section at all and would be satisfied by any section reporting two — alongside `assertNotIn("mcpServers  : skipped (not found)", output)`, a literal match on agy's exact column padding.

This is one divergence, not two: a helper written twice, and one story's later correction that never propagated back.

## Decision
Lift both helpers to module scope in `plugins/recallum-memory/tests/test_plugin.py` as `_agy_validate(directory) -> tuple[int, str]` and `_agy_report_line(output, section) -> str`, and route all four call sites through them. `_agy_validate` returns the exit code alongside the merged output so each caller takes what it needs, which is the difference that blocked reuse in the first place.

Apply S004's ruling to S001's assertions: assert the anchored per-section report line exists and does not say "skipped", rather than matching a bare count or agy's padding.

Do not extend this to `agy plugin install`. `test_agy_plugin_install_copies_mcp_config_into_isolated_home` is a different subcommand with a different environment (an overridden `HOME`) and one call site.

## Alternatives considered
- Leave the four copies: rejected. This is mechanical duplication of one invocation of one binary with identical flags — not two things that merely look alike — and the `4ef08bc` correction stalling inside one class is direct evidence that the copies drift.
- Keep `_validate` as a `staticmethod` on `AntigravityHookGapTests` and have `AntigravityMcpConfigTests` call it across classes: rejected; a helper reached through an unrelated test class's namespace is worse than either duplication or module scope.
- Have `_agy_validate` return `CompletedProcess`: rejected; the `stdout + stderr` merge is itself part of what was duplicated, and leaving it to callers keeps the duplication while adding a helper.
- Preserve S001's `assertIn("2 processed", ...)` and only extract the subprocess call: rejected; it would leave the batch holding two opposite rulings on the same assertion, one of them already overturned by the batch.
- Assert the skills line reports a *non-zero* count, which neither story does: rejected as a third variant invented at consolidation time rather than taken from the batch.

## Consequences
S001 no longer asserts that exactly two skills are processed. That was never the assertion it wanted — it wanted the section to be processed rather than skipped, which the anchored line now states directly and without depending on the skill count or on agy's column widths. A regression that dropped a skill would be caught by `test_skills_and_mcp_servers_unaffected_by_hooks_json_presence` comparing report lines across two bundles, not by a literal.

`_agy_report_line` raises `AssertionError` from a bare `assert` rather than failing through `unittest`, so a missing section surfaces as an error rather than a failure. That is S004's original behaviour, preserved deliberately.

All four call sites remain behind `@skipUnless(AGY, ...)`, and `_agy_validate` re-asserts `AGY is not None` for the type checker. The helper is unguarded on its own: calling it without the decorator fails on the assert rather than skipping. With `agy` v1.1.19 present these tests run rather than skip, and the suite is unchanged at 179 passed, 92 subtests.
