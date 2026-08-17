# S002 — Hygiene guidance: explicit stale resolution, merge-vs-update, and the no-auto-merge contract

## Actor
An MCP agent using the `session-start`, `capture-scan`, and `stale-review` prompts; the plugin skill and `SessionStart` hook reminder as guidance consumers.

## Objective and motivation
Agents write faster than the corpus is cleaned. `similar`, the stale queue, `reconfirm`, `update`, and `merge_memories` already exist, but the guidance is easy to skip, so semantic duplicates, unresolved contradictions, and stale facts degrade recall and context without failing anything. Harden the actionable guidance so every reviewed stale item ends in an explicit resolution and `similar` reconciles as merge-vs-update — while the server never auto-resolves.

## In scope
- `stale-review` prompt: require that every reviewed stale item conclude with exactly one of `reconfirm` (still true), `update` (changed), `forget` (no longer applies), or `merge_memories` (restatement of an active claim); no "already looked, no action" terminal state.
- `capture-scan` prompt: require reading the `similar` field from `remember`/`remember_batch` outcomes and reconciling — merge for restatements/refinements of the same claim, update/forget of the wrong claim for contradictions or incorrect facts, never auto-resolving.
- Skill (`plugins/recallum-memory/skills/recallum-memory/SKILL.md`) and the `SessionStart` hook reminder (`hooks/recallum_hook.py`): same criteria — `related_memories` as an optional neighbourhood step only when needed; prefer `reconfirm` over re-storing identical content; the three prompts named as workflow shortcuts where the client supports MCP prompts.
- Contract tests asserting the key guidance text in prompts, skill, and hook.
- Verification that the server still does not auto-merge or auto-forget when `similar` is reported.
- Relevant unit/plugin suite green.

## Out of scope
- Auto-merge, auto-forget, or changing `similar_min_similarity` defaults.
- HTTP self-service for stale queue/neighbours (story S003).
- Ranking, graph, or new MCP tools; runtime semantics of `similar`.

## Mapped OpenSpec tasks
Source change: `improve-memory-corpus-hygiene` — tasks 1.1, 1.2, 1.3, 3.1, 4.1, 4.2.

## Dependencies
No story dependency. Builds on the existing three allowlisted prompts in `recallum/mcp/server.py` and the existing skill/hook guidance.

## Acceptance criteria
- Retrieving the `stale-review` prompt returns text that demands each verified stale item conclude with exactly one of `reconfirm`, `update`, `forget`, or `merge_memories`; the text contains no terminal "no action" outcome for a verified item.
- Retrieving the `capture-scan` prompt returns text that instructs reading `similar` and distinguishing merge (same claim restated) from update/forget (contradiction or incorrect fact) without auto-resolving.
- The prompt set remains exactly `session-start`, `capture-scan`, `stale-review`: the existing startup validation still fails when a fourth prompt name is registered.
- `SKILL.md` and the `SessionStart` hook text contain the merge-vs-update criterion and the stale-resolution requirement; the plugin/unit contract tests assert these key strings and fail when the text is removed.
- A test asserts that when `remember`/`remember_batch` reports `similar`, the new memory is persisted per current rules and none of the similar memories is mutated by the server — passing with no auto-merge and no auto-forget.
- The relevant suites are green: `tests/unit` and `plugins/recallum-memory/tests`.

## Assumptions
- Guidance text stays in English (the prompt/skill language of this repo).
- "Explicit per-item resolution" is a guidance-text requirement; server behavior and staleness thresholds are unchanged.

## Open questions
- Should the `SessionStart` hook text be identical across all client variants (Cursor, Codex, Claude Code, Grok Build), or may per-client wording differ as long as both criteria are present?

## Affected surface
`recallum/mcp/server.py` prompt strings, `plugins/recallum-memory/skills/recallum-memory/SKILL.md`, `plugins/recallum-memory/hooks/recallum_hook.py`, plugin and unit contract tests.

## Risks
Longer guidance → lower compliance: keep the rules short and the resolutions explicit, not essays.

## Validation expectations
Unit and plugin suites green; contract tests on prompt/skill/hook key text; MCP prompt discovery returning exactly three prompts.

## Boundary crossings
MCP agent integration and agent-session-bootstrap guidance surfaces. No HTTP, persistence, or ranking changes.
