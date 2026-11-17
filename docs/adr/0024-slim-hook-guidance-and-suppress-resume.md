# ADR 0024: Slim hook guidance, bound initial context, and suppress resume re-injection

## Status
Accepted (refines ADR 0015)

## Context
Evidence from 150 Factory Droid sessions showed that hook text alone was not the dominant token cost; hook-driven MCP tool amplification was roughly 8x larger (~2.64M chars from `context` and `recall` results vs ~334k chars of injected hook text across 100 sessions):
- Because client harnesses store MCP credentials in client configs rather than shell env vars (`RECALLUM_MCP_URL`, `RECALLUM_API_KEY`), inline Context Digest fetching fell back 171 of 171 times to instructing an unbounded `context` call (server default `context_default_max_chars = 6000`, ~8.8 KB per result).
- `SessionStart` matched `startup|resume|clear|compact`. In 82 `resume` events (plus 8 sessions where Droid fired `startup` and `resume` back-to-back within ~300 ms, doubling the injected text to 3,416 chars), agents repeatedly re-called `context` even though memory was already present in the resumed conversation.
- Under ADR 0015, hooks repeated detailed write, merge, and stale-resolution instructions (`WORKFLOW_HINT`) on every `SessionStart` (~1,707 chars) and `UserPromptSubmit` (~561 chars), and `UserPromptSubmit` lacked cooldowns or system-notification filtering.

## Decision
1. Keep ADR 0015's surface separation and zero-dependency hook constraint, but delegate detailed write/merge/stale-resolution rules out of hooks into `SKILL.md` and MCP prompts; hooks emit only the project key, bounded read guidance, English-language rule, and a pointer to read the `recallum-memory` skill before writing.
2. Bound fallback initial `context` calls in hook guidance and `rules/recallum-memory.mdc` to `max_chars=2000` and `max_items=10` (skipping trivial/self-contained turns), and keep Context Digest fetching strictly opt-in via environment variables rather than reading third-party harness credential files.
3. Suppress `resume` re-injection by removing `resume` from the `SessionStart` hook matcher (`startup|clear|compact`) and treating `source == "resume"` as a no-op in `recallum_hook.py`.
4. Store ephemeral per-session state under `tempfile.gettempdir()` keyed by session/project hash to deduplicate back-to-back `SessionStart` emissions (resetting on `clear` and `compact`), enforce a `UserPromptSubmit` cooldown (5 turns / 10 minutes), and ignore internal system/subagent prompt payloads.

## Alternatives considered
- **Reading `~/.factory/mcp.json` (or other harness configs) inside the hook for automatic digests**: rejected to avoid coupling a fail-open hook to third-party secret storage formats.
- **Removing `UserPromptSubmit` completely**: rejected because a terse, cooled-down Memory Signal reminder helps on genuine late-session preference/decision shifts.
- **Keeping `WORKFLOW_HINT` inline in `SessionStart`**: rejected because ~1,300 chars per session and duplicated `startup`+`resume` payloads add noise without preventing agents from needing `SKILL.md` anyway.

## Consequences
- Contract tests that previously asserted `WORKFLOW_HINT` and full merge/reconfirm/stale phrasing inside `recallum_hook.py` (`test_plugin.py` and `test_agent_synergy.py`) must be updated to verify the slimmed hook contract while keeping S002 coverage in `SKILL.md` and `prompts.py`.
- Initial `context` tool calls return ~2 KB–3 KB instead of ~8.8 KB unless the agent explicitly requests deeper focus/history.
- Resumed sessions no longer re-inject hook text or trigger redundant `context` calls; `/clear` and `/compact` reset the ephemeral session state and re-inject normally.
