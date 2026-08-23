# QA plan — S001: Add a validated MCP config to the Recallum plugin bundle

## Risks and cheapest detection layer

1. **Highest — `mcp_config.json` fails `agy plugin validate` or regresses `skills: 2 processed`.**
   Cheapest: **static/CLI check** (not unit, not integration — a single deterministic CLI
   invocation against the checked-in file). Running the real `agy` binary here is cheap,
   fast, and the only oracle that matters: `agy`'s parser is a closed-source Go binary, so a
   hand-written JSON-schema unit test could pass while the real parser still rejects the file.
2. **High — the new bundle-root `mcp_config.json` collides with, or is confused with, the
   legacy `mcp.json` / `.mcp.json`.** Cheapest: **unit-level file-content assertion** in
   `test_plugin.py` — read all three files and assert (a) `mcp_config.json` uses the
   `serverUrl` shape, (b) `mcp.json` / `.mcp.json` are untouched (byte-identical to their
   current content) and still use the legacy `type`/`url` shape, (c) `agy plugin validate`
   (CLI check, not unit) still succeeds with all three files present, proving Antigravity's
   parser ignores files it doesn't look for rather than erroring on an unrecognized second
   MCP file in the same directory.
3. **High — placeholder/templated header value is mistaken for or promoted to a real secret.**
   Cheapest: **unit-level string assertion** — the committed file's `Authorization` header
   value must not equal, or be derived from, any real token; assert it matches an explicit
   placeholder pattern (e.g. an obvious non-secret literal or the same `${...}` interpolation
   syntax already present in `.mcp.json`/`mcp.json`). A `git diff`/`git grep` check for
   high-entropy strings in the new file is a cheap second unit-level guard.
4. **High — OQ4 runtime probe gives a false "honoured"/"not honoured" verdict, or silently
   mutates the developer's real Antigravity state.** Cheapest layer for the mutation risk is
   **procedural isolation** (not a test at all — a documented manual procedure with an
   isolation contract, see below); this is not automatable because it depends on interactive
   CLI behavior (theme.md constraint 7: hooks/tool availability are not observable headless).
5. **Medium — `plugin.json` regresses (new required-looking fields, encoding, trailing
   content) as an incidental side effect of adding a sibling file.** Cheapest: **unit-level**
   round-trip `json.load` of `plugin.json` plus the existing `GROK_MANIFEST`-style assertions
   already in `test_plugin.py`, run before/after the story's diff — this only needs to prove
   the file is byte-identical, so it is a diff check, not new test logic.
6. **Low — bundle install (`agy plugin install`) copies `mcp_config.json` incorrectly (wrong
   permissions, path, or omitted).** Cheapest: **integration-level** — one `agy plugin
   install` into an isolated `$HOME` and inspect the copied file under
   `$HOME/.gemini/config/plugins/recallum-memory/mcp_config.json`. This is integration, not
   unit, because it exercises the real binary's copy semantics, which S001 does not control.
7. **Low — regression to other clients' validation (Codex/Claude/Cursor/Grok manifests) from
   editing shared bundle files.** Cheapest: **unit** — re-run the existing manifest-parity
   assertions in `test_plugin.py` (`CODEX_MANIFEST`, `CLAUDE_MANIFEST`, `GROK_MANIFEST`,
   `CURSOR_MANIFEST` parsing, already present) unmodified; a green run proves no regression
   without writing new code.

## Checks by layer

### Static / CLI-oracle (new, story-specific)
- `agy plugin validate plugins/recallum-memory` from repo root, captured stdout, asserting:
  - `skills      : 2 processed` (unchanged from today's baseline, confirmed live:
    `agy plugin validate plugins/recallum-memory` currently prints exactly that line plus
    `agents`/`commands`/`hooks` "skipped (not found)" and `mcpServers  : skipped (not found)`).
  - `mcpServers` line no longer reads "skipped (not found)"; it must show a processed/ok state.
  - No new error lines (no "must have either command or serverUrl").
  - Exit code `0`.
  - This check has no fake/mocked equivalent — it is the closed-source Go binary's real
    output, so it must run wherever `agy` is present (local dev, and CI if the binary is
    provisioned there).

### Unit (`plugins/recallum-memory/tests/test_plugin.py`)
- New test function (name suggestion: `test_antigravity_mcp_config_shape`):
  - `json.loads((PLUGIN_ROOT / "mcp_config.json").read_text())` parses without error.
  - Top-level shape is exactly `{"mcpServers": {"recallum": {...}}}`.
  - The `recallum` entry has `serverUrl` (not `type`/`url`), matching theme constraint 2's
    shape; assert absence of the `type` and `url` keys specifically, since their presence
    silently reintroduces the rejected legacy shape alongside a valid one.
  - `headers.Authorization` is present and does not equal a live/real secret — assert it is
    either a `${...}`-style placeholder (matching the interpolation scheme already used in
    `mcp.json`/`.mcp.json`) or an explicit non-secret literal (e.g. contains `PLACEHOLDER` /
    `<token>`), never a bare high-entropy string.
- New test function (name suggestion: `test_legacy_mcp_files_untouched`):
  - `mcp.json` and `.mcp.json` still exist, still parse as JSON, and still use the
    `type`/`url` shape (regression guard: nobody "fixes" the legacy files as a side effect of
    this story, which would silently expand its scope).
- Existing manifest tests (`CODEX_MANIFEST`, `CLAUDE_MANIFEST`, `GROK_MANIFEST`,
  `CURSOR_MANIFEST` parsing) re-run unmodified as a regression gate on `plugin.json`.
- Fixtures: none new beyond the repo files themselves — this story needs no fake-CLI stdin
  helper (the L57/L90/L123/L194 helpers exist for install/doctor flows S002/S003 own; S001
  touches no installer or doctor code).

### Integration (`plugins/recallum-memory/tests/test_plugin.py`, subprocess-driven)
- New test function (name suggestion: `test_antigravity_plugin_install_copies_mcp_config`):
  - Isolate `HOME` to a `tempfile.TemporaryDirectory()` (mirrors the existing pattern at
    L1295 `"HOME": str(root)` for the Grok install tests — same isolation idiom, new client).
  - Run `agy plugin install <repo>/plugins/recallum-memory` with that isolated `HOME`,
    skipped via `unittest.skipUnless(shutil.which("agy"), ...)` (see CI divergence below).
  - Assert `$HOME/.gemini/config/plugins/recallum-memory/mcp_config.json` exists, parses, and
    matches the source file's `mcpServers.recallum.serverUrl` value.
  - Assert `agy plugin list` (same isolated `HOME`) lists `recallum-memory` and its
    `mcpServers` component (mirrors constraint 4: `agy plugin list` prints
    `imports[].name`/`components[]`).
  - This is integration, not unit, because it invokes the real `agy` binary end-to-end
    through install → copy → list; a unit test cannot fake Go binary copy semantics.

### End-to-end (manual, OQ4 probe — not automated, not run by this agent)
Named procedure, to be executed and recorded by a human/CI runner with real `agy` access:

1. **Isolate.** `export QA_HOME=$(mktemp -d)`. Every subsequent command in this procedure
   runs with `HOME=$QA_HOME` explicitly prefixed — never the operator's real `$HOME`. Confirm
   isolation first: `HOME=$QA_HOME agy plugin list` must print "No imported plugins." (proves
   `$QA_HOME/.gemini` starts empty and unrelated to the developer's real `~/.gemini`).
2. **Install the bundle alone, no native config.** From repo root:
   `HOME=$QA_HOME agy plugin install plugins/recallum-memory`.
   Confirm no native MCP file exists: `test ! -f "$QA_HOME/.gemini/config/mcp_config.json"`
   must succeed (empty/absent) — this is the "bundle only, no native registration" precondition
   the OQ4 finding depends on.
3. **Start an interactive session and inspect active MCP servers.** Launch
   `HOME=$QA_HOME agy` interactively (not `-p`, not `--input-format stream-json` — theme.md
   constraint 7 established headless mode does not dispatch hooks; AC3(c) requires this run be
   genuinely interactive). Inside the session, use whatever in-CLI surface lists active/loaded
   MCP servers (e.g. a `/mcp` or `/tools` style command if one exists in this `agy` build —
   discover the exact command by trying `agy`'s in-session `/help` first, since it is not
   documented in the repo). Record the exact command tried.
4. **Record outcome and evidence** into `docs/delivery/support-antigravity-cli/S001/oq4-evidence.md`
   (a new file this story's implementer creates, separate from this qa-plan.md — this plan
   only specifies the procedure, not the evidence artifact's content):
   - **(a) Honoured** — `recallum` appears among active MCP servers. Capture: the exact
     in-session listing output, `QA_HOME` value, `agy --version`, timestamp.
   - **(b) Not honoured** — session starts, listing surface works, `recallum` is absent.
     Same evidence set, plus confirmation the listing surface itself proves other servers
     (if any) would have shown up (i.e. the negative isn't just a broken listing command).
   - **(c) Inconclusive** — only after the genuine interactive attempt in step 3 was made
     (per AC3(c), a headless-only attempt never qualifies). Capture the full transcript of
     what was tried, what was observed, and the specific technical blocker (e.g. "no
     in-session command enumerates active MCP servers in this `agy` build", "interactive
     session hung / required a TTY this environment cannot provide", a crash log path).
5. **Teardown.** `rm -rf "$QA_HOME"`. Never touches the operator's real `~/.gemini/` because
   isolation happened at step 1, not at cleanup — cleanup is a hygiene step, not the safety
   boundary. Re-verify no writes escaped isolation: `git status --porcelain` at repo root
   must show no unexpected changes outside the bundle diff and (if created) `oq4-evidence.md`.

## Operational "done" (what stage 8 must run and pass)

1. `python3 -m unittest plugins.recallum-memory.tests.test_plugin -k
   "antigravity_mcp_config_shape or legacy_mcp_files_untouched"` (or the repo's actual
   unittest invocation convention, matched to how `test_plugin.py` is normally run) — exit 0.
2. Full existing suite `python3 -m unittest plugins.recallum-memory.tests.test_plugin` — exit
   0 (regression gate; proves no other client's manifest/hook/doctor test broke).
3. `agy plugin validate plugins/recallum-memory` from repo root — stdout contains
   `skills      : 2 processed` and a processed/ok `mcpServers` line, no error text, exit 0.
   **If `agy` is absent** (no `/home/zozi/.local/bin/agy` or equivalent on `PATH`): this check
   and the integration install test in the previous section are **skipped, not passed** —
   stage 8 must report them as `skipped` with the reason "agy binary not present", and overall
   `pass` requires this skip to be an explicitly acknowledged condition, not silently absorbed
   into a green result. A run with 0 of these checks executed is not "pass".
4. `git diff --stat` limited to: `plugins/recallum-memory/mcp_config.json` (new),
   `plugins/recallum-memory/tests/test_plugin.py` (new test functions only), optionally
   `docs/delivery/support-antigravity-cli/S001/oq4-evidence.md` (new). Any diff touching
   `mcp.json`, `.mcp.json`, `plugin.json`, `install.sh`, `recallum_doctor.py`, or
   `recallum_hook.py` fails stage 8 outright — those are explicitly out of scope per the story.
5. `oq4-evidence.md` exists and its outcome field is exactly one of `honoured` /
   `not_honoured` / `inconclusive`, with the evidence bar for `inconclusive` (interactive
   attempt transcript + named blocker) satisfied per AC3(c) — stage 8 fails if the file is
   absent, or if `inconclusive` is recorded without a genuine interactive-mode transcript.
6. No secret literal in the diff: `git diff | grep -Ei 'bearer [a-z0-9]{20,}'` (or equivalent
   entropy check) returns nothing beyond the accepted placeholder pattern.

## Blocking dependencies

- **`agy` binary** at `/home/zozi/.local/bin/agy` (v1.1.19 confirmed live) or equivalent on
  `PATH`. Blocks checks 3 and the integration install test, and fully blocks the OQ4 probe
  (there is no fake/mock substitute — `agy`'s parser and plugin-copy behavior are closed-source
  and story-critical to prove, not simulate). If CI provisions no `agy` binary, those checks
  degrade to `skipped` with reason recorded (see done-criteria item 3) — CI cannot independently
  certify AC1/AC2/AC3 without it; only the unit-level file-shape assertions (checks in the
  Unit section) run in that degraded mode.
- **A real, human-operated interactive terminal** for the OQ4 probe (step 3 of the E2E
  procedure) — theme.md records interactive mode "blocks" under prior automated attempts, so
  this cannot run inside a headless CI job or this agent's own non-interactive shell. This is
  the one check in this plan that structurally cannot be automated.
- **No network/credential dependency**: the bundle's `mcp_config.json` header is a placeholder,
  not a live token, so no real Recallum server or API key is required to satisfy AC1/AC2/AC5.
  The OQ4 probe only needs the MCP server to be *listed as active*, not successfully called —
  no live server connectivity is required for a honoured/not-honoured verdict, only for a
  deeper "and it actually answers a tool call" check, which is explicitly out of scope for S001.

## Deliberate coverage gaps

- **No test that a tool call through the OQ4-honoured server actually succeeds.** Out of
  scope: S001's AC only requires the server to *appear* among active servers, not that calls
  succeed with a real token — that is a live-connectivity concern for S002/S003, which own
  literal token injection.
- **No CI-automated OQ4 probe.** By design: interactive-mode requirement (constraint 7,
  AC3(c)) makes this structurally unautomatable; recorded as a manual procedure with an
  evidence artifact instead of a test.
- **No fuzz/property test of `mcp_config.json` against `agy`'s full schema** (e.g.
  `disabled`, `disabledTools`, `authProviderType`, `oauth` fields from constraint 2). Out of
  scope: S001 only needs the one shape it uses to validate; broader schema coverage would be
  testing `agy` itself, not this bundle.
- **No test of concurrent/repeated `agy plugin install` runs (idempotency of re-install).**
  Judged low-risk and out of scope: S001 adds a static file, not install logic (that's S002's
  `install_for_antigravity`); if `agy plugin install` itself is non-idempotent, that's a
  pre-existing `agy` behavior outside this bundle's control.
- **No test of `.agents/mcp_config.json` (workspace-scope, theme constraint 1).** Explicitly
  out of scope per story ("Out of scope" section references only S002's native write); the
  spec-review's set-level gap on workspace-scope config was closed in S002, not S001.
