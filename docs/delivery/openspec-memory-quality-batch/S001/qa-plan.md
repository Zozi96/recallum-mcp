# QA plan — S001: Align MCP tool-surface documentation and gate it

## Risks and cheapest detection layer

1. **Critical — the gate never fails when docs regress (false negative).** The checker could look only for the word "nine", or the new test could be silently uncollected by the `unit-plugin` job's marker filter (`-m "not integration and not vertical and not traefik"`) or run under `continue-on-error`. Unit-test the checker logic with induced misalignment; verify CI wiring statically (workflow inspection). Unit is cheapest because the checker is pure text logic; gate wiring can only be proven by inspecting `ci.yml` and required-checks config.
2. **High — the allowlist and the runtime surface drift apart.** If the docs check hardcodes its own eleven-name list while the runtime check (`validate_only_tools_are_exposed` / `EXPECTED_TOOLS` in `tests/unit/test_mcp_tools.py`) uses another, a twelfth tool added to the server would pass docs against a stale list. Unit: assert the docs-check allowlist is literally the same constant as `EXPECTED_TOOLS`; no separate copy.
3. **High — brittle name extraction causes flaky or wrong failures.** README wraps the tool list across two lines (lines 9–10); backticks, trailing commas, headings vs body, case variants all vary. Unit: extract allowlist-matching backtick tokens from the whole file (not line-anchored) and compare as a set; parameterize formatting variants.
4. **Medium — clients.md rule misfires.** Its "Agent usage guidance" intentionally names only a usage subset (`remember`, `recall`, `context`, ...). A rule requiring all eleven everywhere would false-fail; a rule requiring exact-match only for explicit enumerations (contiguous list of ≥2 tool names) needs definition. Unit: fixture passages (subset guidance, complete enumeration, incomplete enumeration, zero mentions).
5. **Medium — the induced-failure proof is unrepeatable at stage 8.** The validator (`execute`, no edits) cannot revert README to induce failure. The induced-fail + pass demonstration must be a committed self-test that copies the real docs to a tmpdir, mutates the copy, and asserts fail/pass. Unit, since it is deterministic file-text logic with no services.

## Checks, fixtures, and layers

- **Unit — aligned surface:** read real `README.md` and `docs/clients.md` from the repo; assert the full eleven-name set appears in README, no count claim of nine, and any explicit enumeration in `docs/clients.md` equals the allowlist set. Uses real docs as fixtures, network-free and deterministic.
- **Unit — induced regression (committed self-test):** tmpdir copies of real docs; assert fail when (a) README reverts to "nine tools", (b) `related_memories` or `reconfirm` is removed, (c) a tenth/twelfth name is added, (d) `docs/clients.md` is deleted; assert the failure message names the document and the missing/extra names; assert pass on the aligned copy. Idempotent — repeated runs give identical results, no clock/random/network.
- **Unit — allowlist consistency:** assert the docs checker imports and uses `EXPECTED_TOOLS` from `tests/unit/test_mcp_tools.py`; no duplicated literal.
- **Unit — boundary matrix:** empty doc, enumeration with 10 or 12 names, duplicate name, name split across a line wrap, name in backticks vs bare, count claims 9/10/11/12, case variants, name in a heading.
- **Repo/CI-inspection (integration-for-the-gate):** `unit-plugin` in `.github/workflows/ci.yml` collects the new test (no `integration`/`vertical`/`traefik` marker on it, so `-m "not …"` keeps it), no `continue-on-error` on the step, and the job sits in the required-checks set (`scripts/check_github_required_checks.sh`). Unit cannot prove CI runs a test; this static inspection is the only local evidence, hence its own layer.

## Operational done criteria

Stage 8 returns pass only when: the full fast lane `uv run pytest tests/unit -m "not integration and not vertical and not traefik"` plus `uv run pytest plugins/recallum-memory/tests` is green; the docs-surface check and its induced-regression self-test pass (fail/pass outputs captured as evidence); the allowlist-consistency test passes; the workflow inspection confirms the check is collected, unskippable, and in required checks; and the recorded local fast-gate run (induced fail then aligned pass) reproduces. Any skipped, retried, or environment-blocked check is fail/block, not pass.

## Blocking dependencies

No runtime, database, credentials, Ollama, or network — the fast lane is deliberately offline. Requires: locked `uv` dev toolchain (Python 3.14), the existing `unit-plugin` job, and the canonical set already present as `EXPECTED_TOOLS`. Only a blocker if the check artifact cannot be collected by `unit-plugin` without an exclusion marker.

## Deliberate coverage gaps

- No real GitHub PR/CI run: the validator is execute-only and cannot push a misaligned branch; wiring is proven by static workflow inspection plus the committed induced-regression self-test.
- No live-server discovery comparison: the story fixes the allowlist as source of truth; runtime surface is already covered by `test_mcp_tools.py`.
- No markdown rendering, link, or formatting checks; no full-tree scan for tool mentions (both out of scope by story).
- No `scripts/validate_external_mcp_clients.sh` integration: it needs real client CLIs and is not a fast-lane check.
