# QA plan — S002: Hygiene guidance (explicit stale resolution, merge-vs-update, no auto-merge)

Surface is prompt/skill/hook text plus plugin and unit contract tests; no HTTP, persistence, or ranking changes. The acceptance criteria are text-containment statements, so nearly every check is unit- or plugin-level string logic; only the no-auto-merge verification needs a service/integration layer.

## Risks and cheapest detection layer

1. **Critical — prompt name kept, semantics silently weakened (false negative).** The existing discovery test asserts prompt *names* only (`test_discovery_announces_exactly_eleven_tools_and_three_prompts`), so `stale-review` could keep its name while its text regresses to a "no action" terminal state or `capture-scan` keeps ignoring `similar`. Unit: assert on the actual text returned by `stale_review()` and `capture_scan()` in `recallum/mcp/server.py` — pure string functions, deterministic, network-free.
2. **High — guidance text becomes unsatisfiable or self-contradictory.** "Exactly one of reconfirm/update/forget/merge_memories" co-existing with a "already looked, no action" or "skip" terminal state contradicts the rule; "zero items is valid" must survive in `capture-scan` without licensing "no resolution" for *verified* stale items. Unit: forbidden-phrase assertions ("no action", "skip", "leave as is", "do nothing", "already reviewed") scoped to the verified-stale-item branch; required-verb assertions (all four of `reconfirm`, `update`, `forget`, `merge_memories` as the only terminal options).
3. **High — merge-vs-update criterion missing from one guidance surface.** Skill step 8 already covers `similar`, but `capture-scan` and the hook `WORKFLOW_HINT` do not. The story requires the criterion in prompts, skill, *and* hook; per-client hook variants (Grok/Claude/Cursor/plain, env-var selected) each must carry it. Unit (plugin): read the real hook with each client env var set and assert both criteria in every variant; unit: assert `similar` appears in the `capture-scan` prompt.
4. **High — guidance edit regresses existing contract tests.** Prompt edits touch code the allowlist validation reads (`validate_only_tools_are_exposed`, `ALLOWED_PROMPTS`); skill/hook edits touch strings the plugin suite asserts (hook event names `SessionStart`/`UserPromptSubmit`, prompt names in skill, per-client install flows). Regression-only: the existing `tests/unit/test_mcp_tools.py` and `plugins/recallum-memory/tests/test_plugin.py` must stay green unmodified.
5. **Medium — server auto-resolves despite the guidance being text-only.** Story scopes the change to text but *verifies* no auto-merge/auto-forget. Auto-resolution would be a service-layer bug (no HTTP involved). Unit: service-level test with a fake repository whose `similar_active` returns a deterministic pair — assert the new memory is created and no `update`/`forget`/`merge` call targets the similar ids, for both `remember` and `remember_batch`. Integration: existing `test_remember_flags_a_similar_existing_memory` (real pgvector repo) stays green as the honest regression proof that real `similar` still surfaces without mutation.

## Checks, fixtures, and layers

- **Unit — `stale-review` prompt text:** call `stale_review()` from `recallum/mcp/server.py`; assert all four resolution verbs (`reconfirm`, `update`, `forget`, `merge_memories`) are named as the terminal outcomes for each verified stale item, and that no forbidden no-action phrasing appears in the same sentence/branch. Assert on lowercased text (case-insensitive) to avoid brittle matching.
- **Unit — `capture-scan` prompt text:** assert it mentions reading the `similar` field on `remember`/`remember_batch` outcomes; distinguishes merge (restatement/refinement of the same claim) from `update`/`forget` (contradiction or incorrect fact); never auto-resolves; still permits "Zero items is valid."
- **Unit — `session-start` prompt text:** unchanged surface; assert it still instructs `context` (+ optional `focus`) then `recall` — guards accidental rewrite while editing neighbors.
- **Unit — prompt-set allowlist (regression):** existing `test_validate_only_tools_are_exposed_rejects_a_prompt` and `test_validate_only_tools_are_exposed_allows_the_three_workflow_prompts` and the discovery test remain green with no edits.
- **Plugin/unit — skill text:** read the real `plugins/recallum-memory/skills/recallum-memory/SKILL.md`; assert it names `similar` as a required read on remember/remember_batch outcomes, merge for restatements, `update` for contradictions (never merge contradictions), `reconfirm` preferred over re-storing identical content, and the three prompt names as workflow shortcuts (the latter two already asserted at `test_plugin.py:260–270, 1027–1030` — keep green).
- **Plugin/unit — hook text per client:** run the hook's hint builder with `GROK_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, `PLUGIN_ROOT`-only, and unset env (Cursor) fixtures; assert the emitted `SessionStart` hint contains both the exact-one-of stale-resolution criterion and the merge-vs-update criterion in **each** variant. Uses real `recallum_hook.py`; no network.
- **Unit — no-auto-merge at service layer:** fake repository returns `similar` (content restatement and a contradiction pair) from `similar_active`; assert `remember`/`remember_batch` create/persist the new memory per current rules and call neither merge/update/forget on any similar id. Deterministic embeddings via `tests/embedding_stub.py`/fakes.
- **Integration — real repo (regression):** existing `test_remember_flags_a_similar_existing_memory` in `tests/integration/test_db.py` stays green; if extended, also assert the similar memory's content/`reconfirmed_at` are unchanged after the write.

## Operational done criteria

Stage 8 returns pass only when, executed in this repo with no services required for the fast lane:
1. `uv run pytest tests/unit -m "not integration and not vertical and not traefik"` is green and includes the three prompt-text contract tests, the service no-auto-merge test, and the unmodified allowlist/discovery tests.
2. `uv run pytest plugins/recallum-memory/tests -q` is green, including the new skill/hook text-contract tests asserting both criteria per client variant and all pre-existing plugin tests.
3. A single report line records, per surface, the exact substrings asserted (the four verbs + no forbidden no-action phrasing; `similar` + merge-vs-update; per-client hook variants all carrying both criteria).
4. If a Postgres+pgvector instance is reachable, the integration lane including `test_remember_flags_a_similar_existing_memory` is green; if not, that lane is reported `blocked`, never `pass`.

Any skipped, `continue-on-error`, or environment-substituted check is fail/block, not pass.

## Blocking dependencies

Fast lane needs only the locked `uv` dev toolchain (Python 3.14); it reads real source files as fixtures and is fully offline. The integration lane needs Postgres+pgvector (`RECALLUM_TEST_DATABASE_URL` or Docker, existing `integration` marker) — the no-auto-merge *hard* gate is the unit service test, so the DB is not a blocker for stage 8. No credentials, network, or external clients.

## Deliberate coverage gaps

- **No agent-behavior measurement:** nothing proves a model actually *performs* the resolution; only that guidance text demands it. Compliance is model-dependent and not deterministically testable.
- **No per-client verbatim hook parity:** the open question (identical wording across clients vs. variants) is resolved to "both criteria present in every variant"; exact word-for-word identity across Cursor/Codex/Claude/Grok variants is not asserted.
- **No `similar` runtime semantics changes:** thresholds, embedding model, and stale-queue computation are untouched and unverified here (existing suites cover them).
- **No end-to-end/HTTP checks:** story surface is guidance and plugin tests only; no live MCP client session is exercised.
- **No new negative prompt test beyond `similar` wording:** the "never auto-resolve" phrase itself is asserted, not the full `remember` error-matrix (out of scope).
