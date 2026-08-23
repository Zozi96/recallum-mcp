# S004 — Antigravity hook parity or documented gap for `recallum_hook.py`

## Actor
The Antigravity CLI hook runtime invoking `recallum_hook.py` at `SessionStart`/tool-use events (if it does so at all); an Antigravity CLI user relying on injected Recallum context or, failing that, on skill-only guidance.

## Objective and motivation
Every other supported client gets memory context injected via a hook (`recallum_hook.py`'s per-client detection, prefix, and output branch). Whether Antigravity can get the same treatment is blocked on three unresolved facts: OQ1 (do `SessionStart` hooks fire in interactive sessions, and with what stdout contract), OQ2 (what MCP tool-name prefix Antigravity exposes), and OQ3 (what env var identifies the plugin root to a hook process). The theme's own fallback is explicit: if hooks cannot be proven to work, ship skill-only guidance as a documented gap rather than a silently broken hook.

## In scope
- Running the OQ1/OQ2/OQ3 experiments needed to decide which branch below applies (an interactive `agy` session with an installed `hooks.json`, inspecting `ANTIGRAVITY_CONVERSATION_ID` and any plugin-root env var, capturing actual stdin/stdout on a dispatched hook).
- **If hooks are proven to fire interactively with an observable output contract:** a `hooks.json` in the object schema (constraint 5, `{"SessionStart":{"hooks":[...]}}`, not an array), an Antigravity branch in `recallum_hook.py`'s client detection (`_tool()`), a new `ANTIGRAVITY_TOOL_PREFIX` constant (mirroring `CODEX_TOOL_PREFIX`/`GROK_TOOL_PREFIX`), and an output branch using the binary's actual field names (`injectSteps`/`ephemeralMessage`/`userMessage`/`systemMessage`/`decision` — not `additionalContext`/`hookSpecificOutput`, which constraint 6 states do not exist for this client).
- **If hooks cannot be proven to fire (or fire with no usable output field) in interactive mode:** a documented statement of that gap (which this story's evidence establishes), plus confirmation that skills still load without the hook (skills are plugin content, independent of `hooks.json`), so the user is not silently worse off.
- Test coverage for whichever branch applies: a fake-CLI stdin fixture for Antigravity in `test_plugin.py` if hooks work; a regression test asserting skill loading is unaffected either way.

## Out of scope
- The installer or doctor writing/checking `hooks.json` (S002/S003 territory if hooks land; this story only defines the hook file and runtime behavior itself).
- Bundle `mcp_config.json` (S001) and native MCP registration (S002).
- Any change to hook behavior for existing clients (Codex, Claude Code, Grok, Cursor).
- Documenting the outcome in `docs/clients.md` or the setup skill (S005 owns docs; this story owns the runtime code or gap finding that S005 documents).

## Dependencies
Gated on its own OQ1/OQ2/OQ3 findings, which this story is responsible for producing, not on any other story landing first. Independently deliverable either way: shipping "documented gap + skills confirmed unaffected" is a complete, valid delivery of this story, not a placeholder for a future one. S005 depends on this story's outcome (see S005's Dependencies) to write the hooks section of the docs truthfully.

## Acceptance criteria
- Exactly one of the two outcomes below is recorded with reproducible evidence (command transcript or log excerpt), not asserted from the theme brief alone:
  - **Parity outcome**: an installed `hooks.json` in the object schema produces a dispatched `SessionStart` hook in an interactive `agy` session (not `-p`/headless, per constraint 7's negative result there), and the hook process receives at least one of `conversationId`/`workspacePaths`/`transcriptPath` on stdin; `recallum_hook.py` detects the Antigravity client (via the OQ3 env var or `ANTIGRAVITY_CONVERSATION_ID`) and emits output using a field this story confirms the binary reads (`injectSteps` or another observed field), evidenced by the injected content appearing in the model's context.
  - **Gap outcome**: after at least one genuine interactive-mode attempt, no dispatched hook is observed; the gap is recorded with what was tried and what was observed (not merely "OQ1 unresolved"), and a test confirms Antigravity's skills (from the plugin bundle) still load with no `hooks.json` installed or with a non-firing one present.
- `hooks.json`, if shipped, validates under `agy plugin validate` without the array/object schema error from constraint 5.
- If a tool-name prefix constant is added, at least one existing test asserts its exact string value (matching the pattern of the existing prefix assertions at `test_plugin.py` L1045-1048).
- No change to any existing client's hook detection, prefix, or output branch is introduced by this story (existing hook tests for Codex/Claude/Grok/Cursor still pass unmodified).
