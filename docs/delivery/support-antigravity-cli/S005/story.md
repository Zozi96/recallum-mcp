# S005 — Document Antigravity CLI support and update client-list strings

## Actor
A prospective or existing Recallum user reading `docs/clients.md`, the `recallum-setup` skill, or `README.md` to decide whether/how to connect Antigravity CLI; `agy plugin validate`/marketplace tooling reading `plugin.json` and `.grok-plugin/plugin-index.json` metadata strings.

## Objective and motivation
Recallum's docs currently enumerate Codex, Claude Code, Grok Build, and Cursor as supported clients (`docs/clients.md` H2s, `recallum-setup/SKILL.md` "Setup — <Client>" sections, README tables). Once Antigravity support exists in some form (S001-S004), a user has no way to discover it, get setup instructions, or see accurate tool-name syntax to use in prompts.

## In scope
- A `docs/clients.md` section for Antigravity CLI matching the existing per-client H2 structure (title, tool surface, setup pointer).
- A `Setup — Antigravity CLI` H2 in `plugins/recallum-memory/skills/recallum-setup/SKILL.md`.
- README rows/table entries (`README.md` L3/L61 area) and the tool-name-prefix table entry using whatever prefix constant S004 establishes (or a stated "not available" if S004's outcome is the documented gap).
- `plugins/recallum-memory/plugin.json` description/keywords, `.grok-plugin/plugin-index.json` `mcpServers` description text, and `scripts/validate_external_mcp_clients.sh` updated to include Antigravity in whatever client-list validation it performs.
- The security note about literal-token storage (constraint 3) stated in the Antigravity setup doc, matching how Cursor's/Grok's env-var-reference requirement is already documented for those clients.

## Out of scope
- Any code change to installer, doctor, bundle, or hook runtime (S001-S004 own their own code).
- Marketing or positioning language beyond factual setup/capability description.
- Translating docs to non-English.

## Dependencies
Depends on S001 (bundle config exists and its OQ4 finding), S002 (installer flag/target name and file paths), S003 (doctor client name and check list), and — most materially — **S004's outcome**, since the hooks section cannot be written truthfully until S004 records either working hook parity (with the actual prefix and output contract) or the documented gap. This is a real ordering dependency, not a formality: writing this story's hooks section before S004 lands risks documenting behavior that OQ1-OQ3 have not yet confirmed. The non-hooks sections (install command, doctor check names, security note) can be drafted once S001-S003 land even if S004 is still open, but the story as a whole should not be marked complete until S004 has produced its outcome to document. This is the one place in the five-story split where a documentation story cannot be independently completed ahead of the code story it describes — call this out explicitly during review rather than treating S005 as parallel-safe with S004.

## Acceptance criteria
- `docs/clients.md` contains an Antigravity CLI H2 stating the exact `--target antigravity` install command, the native config path (`~/.gemini/config/mcp_config.json`), and the literal-token security note.
- `recallum-setup/SKILL.md` contains a `Setup — Antigravity CLI` H2 with step-by-step instructions a reader can follow using only what's in the doc (no undocumented prerequisite steps).
- The tool-name table (wherever it lives per-client, e.g. alongside `CODEX_TOOL_PREFIX`/`GROK_TOOL_PREFIX` documentation) states either the exact Antigravity prefix string S004 established, or explicitly "hooks not available for Antigravity CLI; use skill-driven tool discovery" if S004's outcome was the gap — never silent omission.
- `README.md`'s client list/table includes Antigravity CLI as a row with the same columns as the other four clients.
- `plugin.json` and `.grok-plugin/plugin-index.json` client-list strings mention Antigravity CLI where they currently enumerate Codex/Claude/Grok/Cursor.
- `scripts/validate_external_mcp_clients.sh` includes Antigravity in whatever it validates for the other four clients, and passes when run against the finished S001-S004 state.
- No doc states hook behavior for Antigravity that contradicts S004's recorded outcome — a reviewer can check S004's story file's acceptance-criteria outcome against every hook-related sentence in the docs added here.
