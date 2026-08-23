# QA plan — S005: Document Antigravity CLI support and update client-list strings

## Surface inventory (deliverable of this plan)

Every location in the repo that currently enumerates the four/five-client list, found by reading
each target file, not by presuming the theme.md anchor table is current:

| # | File | Location(s) touched | Current state (verified) |
| --- | --- | --- | --- |
| 1 | `docs/clients.md` | H1 title L1 (`Cursor, Grok Build, Codex, and Claude Code`); intro L12 (`install.sh for Codex, Claude Code, and Grok Build`); per-client H2s at L17 (Grok), L55 (Codex), L69 (Cursor), L90 (Claude Code) — Antigravity needs a new H2; tool-name-prefix paragraph ~L127 (`Codex ... Claude Code ... Grok Build ... Cursor ...`) |
| 2 | `plugins/recallum-memory/skills/recallum-setup/SKILL.md` | `Setup — Codex` L43, `Setup — Claude Code` L60, `Setup — Cursor` L104, `Setup — Grok Build` L126 — Antigravity needs a new `Setup — Antigravity CLI` H2 |
| 3 | `plugins/recallum-memory/README.md` | intro L7 (`Cursor, Grok Build, Codex, and Claude Code`); marketplace table L20-25 (Client / Marketplace index / Plugin metadata rows); tool-prefix table L381-388 (`Codex`, `Claude Code (plugin)`, `Claude Code (native/Desktop)`, `Grok Build`, `Cursor` rows) |
| 4 | `README.md` (repo root) | L3 (`Cursor, Codex, Claude Code, and Grok Build`); L61 (`docs/clients.md for wiring up Cursor, Codex, Claude Code, and Grok Build`) |
| 5 | `plugins/recallum-memory/plugin.json` | `description` string (L4, lists all four clients by name); `keywords` array (`grok`, `cursor`, `codex`, `claude-code`) |
| 6 | `.grok-plugin/plugin-index.json` | `components.skills[name=recallum-setup].description` (`"...for Cursor, Grok Build, Codex, or Claude Code."`); `components.mcpServers[0].description` (mentions Grok Build specifically, not an enumeration — verify whether Antigravity needs a mention here at all, since this file is Grok's own marketplace index, not a universal client list) |
| 7 | `scripts/validate_external_mcp_clients.sh` | hardcoded echo L9: `"Required clients: Codex, Claude Code, Cursor"` — **already omits Grok Build today**, a pre-existing gap this story did not create and is not obligated to fix, but must not silently extend the same omission to Antigravity if it touches this line at all |

7 files, 13 distinct locations. This inventory itself must be re-verified by whoever implements
S005, since line numbers shift the moment any file is edited — treat line numbers above as of this
plan's authoring, not as post-edit anchors.

## Risks, ranked, with cheapest layer

1. **Silent omission on one of the 13 locations** (highest — this is the story's core risk). Cheapest
   layer: static grep/string-presence check per file (unit-equivalent). Catches "forgot a file"
   before any human reads prose.
2. **Cleartext-key security note (constraint 3) missing or diluted in the Antigravity section of
   `docs/clients.md`.** Real user-harm risk (API key committed to a tracked `.agents/` path).
   Cheapest layer: string-presence check scoped to the Antigravity H2's line range specifically
   (not "exists somewhere in the file") — a document-scoped grep, still unit-equivalent, but must
   not pass on the note existing in Cursor's or Grok's section instead.
3. **Hooks section contradicts S004's actual outcome.** Cheapest layer: integration-equivalent —
   cross-reference the doc's hook prose against the real repo state (source of truth is the shipped
   code, not this story's assumption), described below. Cannot be caught by string presence alone;
   requires comparing two artifacts.
4. **Tool-name prefix stated wrong or omitted** (depends on S004's `ANTIGRAVITY_TOOL_PREFIX`, if any).
   Same integration-equivalent cross-reference as #3.
5. **S005 marked complete before S004 has landed/recorded its outcome** — an ordering violation the
   story itself flags as its one non-parallel-safe dependency. Cheapest layer: a precondition gate
   before any other check runs (see Blocking dependencies).
6. **Anchor rot**: inserting a new H2/table row shifts every subsequent line-number anchor cited in
   `theme.md`'s Extension Points table and in this very inventory. Low severity (nothing breaks
   functionally) but affects reviewability. Human-review layer: a reviewer diff-reads the touched
   files rather than trusting stale line numbers.
7. **Marketplace-metadata drift** (`plugin.json`, `.grok-plugin/plugin-index.json`) causing
   `agy plugin validate` or Grok's own marketplace parse to choke on a malformed edit. Cheapest
   layer: unit-equivalent — `python3 -c "import json,sys; json.load(open(f))"` on both files (JSON
   validity), plus the existing `agy plugin validate plugins/recallum-memory` / Grok marketplace
   load if available (integration-equivalent, environment-gated — see below).

## Can `scripts/validate_external_mcp_clients.sh` carry the completeness check?

**No.** Read in full: it is a live-server smoke test (Task 10.1 harness) that curls a real
`RECALLUM_URL` with `ALICE_KEY`/`BOB_KEY` and shells out to `smoke_test.sh`; its "Required clients"
line is an informational echo, not a doc-consistency check, and it exits `PENDING` (2) whenever
`RECALLUM_URL`/keys aren't set — which is its normal state in this repo today. It does not read
`docs/clients.md`, `SKILL.md`, `README.md`, or either JSON manifest, so it structurally cannot
detect a missing Antigravity mention in any of those files. Repurposing it would conflate two
unrelated concerns (runtime client auth smoke test vs. static doc-string completeness) and make an
already-PENDING-by-default script the gate for something it can't see.

The story's own AC7 ("includes Antigravity in whatever it validates ... passes when run against the
finished S001-S004 state") is satisfiable narrowly: update the L9 echo string to add Antigravity
(so the script's own self-description doesn't misstate its scope — and while touching that line,
do not silently perpetuate the pre-existing Grok omission; that's a one-line fix in the same spot,
worth doing since S005 is already editing this line, but is not itself an S005 acceptance
criterion). That satisfies AC7's literal text without pretending the script does completeness
enforcement it cannot do.

**Primary completeness check is therefore new and specified here directly** (a command sequence,
not a new script file — this plan authors no code):

```bash
for f in docs/clients.md \
         plugins/recallum-memory/skills/recallum-setup/SKILL.md \
         plugins/recallum-memory/README.md \
         README.md \
         plugins/recallum-memory/plugin.json \
         .grok-plugin/plugin-index.json \
         scripts/validate_external_mcp_clients.sh; do
  grep -qi antigravity "$f" || echo "MISSING: $f"
done
```
Pass = zero `MISSING:` lines. This is unit-equivalent: fast, deterministic, no network, no live
server — exactly the layer this risk belongs at, per the story's own framing that a sixth client
multiplies places to fall out of sync mechanically, not semantically.

## Layered checks

**Unit-equivalent (string/structure presence, no external state):**
- The 7-file grep loop above (risk #1).
- `docs/clients.md`: extract the Antigravity H2's line range (`sed -n '/^## Antigravity/,/^## /p'`)
  and grep that range specifically for the literal-token / cleartext security phrasing already used
  for Cursor/Grok (risk #2) — must not pass on a match found outside the range.
- `SKILL.md`: `grep -n '^## Setup — Antigravity CLI'` exists exactly once.
- `README.md` (repo) and `plugins/recallum-memory/README.md`: Antigravity appears in the same
  table/list structure as the other four (row count check: count client rows before/after, delta
  = +1, not a net change elsewhere).
- `plugin.json`, `.grok-plugin/plugin-index.json`: JSON still parses (`json.load`).

**Integration-equivalent (cross-artifact truth, doc vs. code):**
- Hooks-section truthfulness against S004 (risk #3, #4): at verification time, inspect the actual
  shipped repo state — does `plugins/recallum-memory/hooks/recallum_hook.py` define an
  `ANTIGRAVITY_TOOL_PREFIX` (or equivalent) and an Antigravity branch in `_tool()`/`_emit()`? Does
  `hooks.json` exist with an Antigravity-relevant entry? This determines which of S005's AC7
  branches is true — **do not presume either branch going in**; read the code S004 actually
  produced. Then diff every hook-related sentence added in `docs/clients.md` and `SKILL.md` against
  that finding: if code shows parity, doc must state the exact prefix string found in
  `recallum_hook.py` (byte-for-byte, not paraphrased); if code shows no Antigravity branch, doc must
  state the "hooks not available ... skill-driven tool discovery" gap language verbatim per AC7,
  never silent omission.
- If a prefix string is documented, it must match `test_plugin.py`'s prefix assertion for
  Antigravity if one exists (mirroring the existing L1045-1048 pattern) — treat the test as the
  second source of truth alongside the source constant; a doc/code/test three-way mismatch is a
  fail even if any two agree.
- `agy plugin validate plugins/recallum-memory` (if `agy` is available in the verification
  environment) — confirms `hooks.json`/`mcp_config.json` shape claims made in the docs aren't
  contradicted by what the CLI itself reports.

**Human-review-equivalent (cannot be mechanically decided):**
- Does the `Setup — Antigravity CLI` H2 in `SKILL.md` actually let a reader complete setup using
  only what's written, no undocumented prerequisite step (AC2)? Requires a person to read it as a
  first-time user would.
- Is the security note's wording clear and correctly scoped (not just present, per the mechanical
  check, but comprehensible and matching the actual write path S002 built)?
- Do the anchor-table line numbers in `theme.md`'s Extension Points section still roughly locate
  the right sections after the edit, for the next story/reviewer's benefit? (Low priority — flag
  as stale if drifted, do not block on it.)
- Does the `.grok-plugin/plugin-index.json` mcpServers description need an Antigravity mention at
  all, given that file is specifically Grok's own marketplace index rather than a universal client
  list? A human judgment call the mechanical inventory can't resolve — recommend: no change needed
  there unless the description makes a claim about "all supported clients" (it currently doesn't).

## Operational done criteria (what stage 8 executes)

Stage 8 returns `pass` only when, in this order:
1. **Precondition gate**: S004's story/spec-review/implementation state is inspected and one of its
   two AC7 branches is confirmed true against the actual repo (not the theme brief). If S004 has not
   yet produced either a parity implementation or a recorded gap finding, stage 8 returns `block`,
   not `pass` — S005's hooks section cannot be honestly written or verified before this exists.
2. The 7-file grep loop above returns zero `MISSING:` lines.
3. The scoped security-note grep against the Antigravity H2's line range in `docs/clients.md`
   matches.
4. `SKILL.md` has exactly one `## Setup — Antigravity CLI` H2.
5. Both README client tables/lists show a net +1 Antigravity row with no unrelated row removed.
6. `plugin.json` and `.grok-plugin/plugin-index.json` still parse as valid JSON and mention
   Antigravity where the other four clients are named (plugin.json description/keywords; the
   `.grok-plugin` file only if the human-review judgment above concludes it needs one).
7. The hooks-section three-way cross-reference (doc vs. `recallum_hook.py` vs. `test_plugin.py`)
   shows no contradiction, using S004's actual shipped branch, not an assumed one.
8. `scripts/validate_external_mcp_clients.sh`'s L9 echo string mentions Antigravity if the file was
   touched at all (AC7's literal requirement); the script's PENDING/live-server exit behavior is
   unchanged and is not itself a blocking dependency for this story's docs-only checks.
9. A human reviewer confirms the `SKILL.md` Antigravity setup section is self-sufficient (no
   undocumented prerequisite).

Any check above that cannot run because S004's outcome is undetermined (step 1) blocks the whole
plan — it is not skippable and not gradeable as partial pass.

## Blocking dependencies

- S004 must have landed (either branch) before step 1 can resolve; this is the story's own stated
  ordering constraint, not new. S001-S003 landing determines whether the non-hooks sections
  (install command, doctor check names) can even be drafted accurately, but do not block the docs
  themselves being internally consistent.
- `agy` CLI availability in the verification environment is optional (used only for the
  `agy plugin validate` cross-check); its absence downgrades that one check to skipped-with-reason,
  not fail, since the story's core claims are checkable from repo state alone.
- No credentials, network, or live Recallum server are required for any check in this plan —
  deliberately, since this is a documentation story and `validate_external_mcp_clients.sh`'s
  live-server dependency is explicitly excluded from the completeness mechanism (see above).

## Deliberate coverage gaps

- **Not testing**: whether the documented `--target antigravity` install command actually works
  end-to-end (that's S002's QA plan's job — this plan only checks the docs describe *some* command
  consistently across surfaces, not that running it succeeds).
- **Not testing**: whether the doctor check names referenced in docs match `recallum_doctor.py`
  byte-for-byte beyond what's needed for the hooks cross-reference (S003's QA plan owns doctor
  correctness).
- **Not testing**: non-English translations (explicitly out of scope in the story).
- **Not testing**: `agy plugin list`/marketplace UI rendering of the updated `plugin.json`
  description in a live Antigravity install — environment-gated, judged not worth the setup cost
  for a description-string change; JSON validity + content match is sufficient evidence.
- **Not fixing**: the pre-existing Grok omission in `validate_external_mcp_clients.sh`'s L9 echo is
  noted but not required to be corrected by this story's acceptance criteria; flagged for the
  implementer as an adjacent one-line opportunity, not a gate.
