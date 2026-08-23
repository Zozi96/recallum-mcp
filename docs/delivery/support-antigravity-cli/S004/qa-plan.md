# QA plan — S004: Antigravity hook parity or documented gap

This story is a determination, not a feature: its acceptance criteria are satisfied by
evidence, not by a green test suite alone. This plan therefore has two tracks —
(A) the interactive experiment that decides which fork applies, and (B) the automated
regression suite that guards whichever fork is taken. Track A produces the evidence the
acceptance criteria demand; Track B is what stage 8 can actually run unattended.

## Risks, ranked

1. **Critical — the fork decision is wrong or unfalsifiable.** If "no hook fired" is
   concluded from a flaky or too-short observation window, a real parity path gets
   discarded (or a broken one gets shipped). Cheapest layer: none — this is inherently a
   manual/E2E determination against the real `agy` binary. No unit or integration test can
   substitute for observing the actual dispatch.
2. **Critical — output field guess is wrong.** Emitting `injectSteps` (or whichever field
   is chosen) without confirming the binary actually surfaces it as model-visible text
   ships a hook that runs, prints JSON, and injects nothing — indistinguishable from "no
   hook" to the user, worse than the documented-gap branch because it looks like it works.
   Cheapest layer: manual interactive observation (the only place "model-visible" can be
   judged) plus a unit test locking the exact field name once confirmed.
3. **High — regression to existing clients.** Adding an Antigravity branch to `_tool()`,
   `_lookup_hint()`, and `_emit()` risks disturbing the Cursor/Codex/Claude/Grok branches
   (e.g. the `or`-chain fallback order, the `_emit` Cursor-special-case). Cheapest layer:
   unit — run the existing `test_plugin.py` hook suite unmodified; any new branch must be
   additive (an `elif`/new top-level `if` returning early), never reordering existing
   checks.
4. **High — `hooks.json` schema regression.** Shipping an array where Antigravity expects
   a single object (constraint 5) breaks validation silently until `agy plugin validate`
   is run. Cheapest layer: unit/static — schema-shape assertion on the JSON file itself,
   no binary needed; then one integration check running the real `agy plugin validate`.
5. **Medium — env var detection collides with another client's env vars.** OQ3's candidate
   (`ANTIGRAVITY_CONVERSATION_ID` or another var) must not be a substring/alias of
   `CURSOR_PLUGIN_ROOT`/`GROK_PLUGIN_ROOT`/`PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`, and the
   detection order in `_tool()` must place Antigravity correctly relative to those
   (mirroring the documented Cursor-before-Grok-before-Codex-before-Claude ordering
   rationale). Cheapest layer: unit — fake env fixture per combination.
6. **Medium — skills silently stop loading.** Because skills are plugin content
   independent of `hooks.json` (per the story's Gap branch), a bug in `hooks.json`
   authoring (e.g. malformed JSON breaking plugin install entirely, not just hook parsing)
   could take skills down with it. Cheapest layer: integration — `agy plugin validate` /
   `agy plugin list` against the actual bundle with the shipped `hooks.json` present.
7. **Low — headless/CI environment has no `agy`.** Any check that shells out to `agy`
   must degrade to skip/fail-visibly, not hang or silently pass. Cheapest layer: unit —
   assert the test harness detects `agy` absence and reports it as blocked, not green.

## Track A — the interactive experiment (OQ1, and the output-field determination)

### Harness

Use `script(1)` for the raw capture (always available, no extra dependency) with a
`pexpect`-driven driver script if `pexpect` is available in the dev environment;
`script` is the fallback that keeps the experiment reproducible without adding a new
Python dependency to a hook file constrained to stdlib-only, older-Python compatibility.

Concretely:

```
HOME=$(mktemp -d)                     # isolate from the developer's real ~/.gemini
mkdir -p "$HOME/.gemini/config/plugins"
cp -r plugins/recallum-memory "$HOME/.gemini/config/plugins/recallum-memory"
# hooks.json under test writes to a private log file, e.g.
#   echo "$(date -Iseconds) DISPATCHED $$" >> /tmp/agy-hook-probe.log
# instead of / in addition to the real recallum_hook.py, so dispatch is provable
# independent of whether the hook's own JSON output is correct.
script -qec 'HOME='"$HOME"' agy' /tmp/agy-interactive-session.typescript &
AGY_PID=$!
# drive via pexpect (preferred) sending a trivial prompt + newline, or manually
# if pexpect is unavailable — see "manual" below
```

Isolation: a scratch `$HOME` so `~/.gemini/config/mcp_config.json`,
`~/.gemini/antigravity-cli/cli.log`, and any session history the developer already has
are never read or mutated. The probe plugin is copied, not the developer's real one.

### What to send, what to capture, how long to wait

- Send one trivial prompt (e.g. `hello`) to force `agy` past `SessionStart` and into an
  active turn, then wait. Budget: 30 seconds of silence on the probe log before
  concluding no dispatch — long enough to rule out slow process spawn (the hook itself
  already runs under a 5s self-imposed timeout per the module docstring), short enough
  to keep the experiment bounded. Run the wait-and-check three times (three separate
  sessions), not once, before concluding a negative — one hung terminal is not evidence.
- Capture: the `script` typescript (raw terminal I/O), the probe log file (proves
  dispatch independent of terminal rendering), and `~/.gemini/antigravity-cli/cli.log`
  from the scratch HOME (proves parse errors are absent, matching how constraint 7 was
  established for headless mode).
- Kill the `agy` process and clean up the scratch HOME after each of the three runs;
  do not leave a hung `script` session as an artifact.

### Falsification conditions (stated explicitly, per the task)

- **Hook DID fire**: the probe log file contains a `DISPATCHED` line with a timestamp
  after the prompt was sent, in at least 2 of 3 runs. This is direct, unambiguous
  evidence — a file write from inside the hook process — not an inference from stdout
  rendering (which `agy` may or may not surface to the terminal).
- **Hook did NOT fire**: after all three runs, the probe log file is empty or unchanged,
  AND `cli.log` shows no parse error (ruling out "hook fired but crashed before writing"
  — that case is a different, narrower finding: "detected but broken", which routes back
  to the Parity branch with a bug, not to the Gap branch).
- **Distinguishing "fired but no visible output" from "did not fire"**: this is exactly
  why the probe writes to a side-channel log rather than relying on `_emit`'s stdout.
  Once dispatch is proven via the probe log, a second, separate run swaps in the real
  `recallum_hook.py` (or a minimal stub emitting one candidate field with an obviously
  unique string, e.g. `"RECALLUM_PROBE_MARKER_7f3a"`) and the transcript is grepped for
  that marker. If the probe log shows dispatch but the marker never appears in the
  `script` typescript across all five candidate fields (`injectSteps`, `ephemeralMessage`,
  `userMessage`, `systemMessage`, `decision`), tried one at a time in five separate runs,
  that is the falsification condition for "no usable output field" — routing to the Gap
  branch's second variant (hook fires, nothing is model-visible) even though dispatch is
  proven.

### OQ2 (tool-name prefix) and OQ3 (plugin-root env var) — how each is determined

- **OQ3**: in the same scratch-HOME interactive session, before/independent of the hook
  experiment, invoke a one-line probe command (`env | sort > /tmp/agy-env-probe.txt`) from
  inside a hook stub itself (since the env is set on the hook's own process, not the
  parent shell) — the stub hook writes `os.environ` to a file. Inspect for
  `ANTIGRAVITY_CONVERSATION_ID` and any `*PLUGIN_ROOT*`-shaped variable. This determines
  OQ3 directly from the process that would actually run in production, not from the
  binary's string table (which only proves the symbol exists, not that it reaches the
  hook's environment).
- **OQ2**: in the same interactive session, ask the model to list or attempt to call a
  Recallum MCP tool (with `mcp_config.json` present per S001) and observe the exact tool
  name surfaced in the transcript/`cli.log`. This is an interactive, not headless, check
  because tool listing behavior may differ between modes exactly as hooks did.

### What is NOT automatable, and why

- The interactive experiment itself cannot be scripted into CI: `agy` in interactive mode
  is a TTY-driven, model-backed session with no documented headless equivalent that
  preserves the exact code path under test (headless is a different code path per
  constraint 7). It requires a human (or a `pexpect` driver run manually by an engineer)
  to execute, and its result is a one-time fact about the binary, not a repeatable
  regression check — once OQ1/OQ2/OQ3 are answered, they do not need to be re-answered
  every CI run, only if `agy` is upgraded.
- Judging "model-visible" for the output-field determination is inherently manual: it
  requires reading the transcript and confirming the injected text reads as context the
  model incorporated, not just JSON that happened to print to a pane. This is recorded as
  evidence (transcript excerpt + marker match), not asserted by a script.
- Recommendation: record the three-runs-times-N-fields experiment as a **manual evidence
  capture**, attached to the story as the transcript/log excerpts the acceptance criteria
  require, executed once by the implementer, re-run only on `agy` version bumps.

## Track B — automated regression suite (what stage 8 runs)

All of Track B is layer: unit, using `test_plugin.py`'s existing fixture patterns
(fake-CLI stdin helpers at L57/L90/L123/L194) as precedent, extended only if the Parity
branch is taken.

### If Parity branch:

1. **Unit** — `_tool()` returns the Antigravity-prefixed name when the OQ3 env var is set,
   with no other client var set. Mirrors existing per-client `_tool()` tests.
2. **Unit** — `_tool()` detection-order fixture: OQ3 var set together with each of
   `CURSOR_PLUGIN_ROOT`/`GROK_PLUGIN_ROOT`/`PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` in turn;
   assert the existing client wins where the story does not claim Antigravity must
   preempt it (no ordering claim = existing precedence holds, since AC requires zero
   change to existing clients' branches).
3. **Unit** — `ANTIGRAVITY_TOOL_PREFIX` constant exact-string assertion, same pattern as
   `test_hook_and_tests_agree_on_all_tool_prefixes` (L1045-1048) and the skill-doc
   assertion (`test_skills_document_the_tool_prefix_of_each_client`).
4. **Unit** — `_emit()` Antigravity branch emits the confirmed field name (from Track A)
   with the digest content, via a fake-stdin fixture new to `test_plugin.py`, following
   the existing per-client fixture shape (`FAKE_CODEX`/`FAKE_CURSOR`/`FAKE_CLAUDE`
   pattern) adapted to set the OQ3 env var instead of spawning a fake binary (since the
   hook reads env, not a CLI subprocess, for detection).
5. **Static/unit** — `hooks.json` parses as JSON and every event key maps to an object
   (not a list) containing a `hooks` list; a regression test that would have caught
   constraint 5's array-vs-object defect by construction.
6. **Integration** — `agy plugin validate plugins/recallum-memory` (real binary, skipped
   with an explicit "blocked: agy not found" result if absent) reports the plugin's
   `hooks` as found/valid, not the current "not found".
7. **Unit** — existing full hook suite (all Cursor/Codex/Claude/Grok tests) passes
   unmodified — this is the explicit AC requirement, run as-is with zero edits.

### If Gap branch:

1. **Integration** — `agy plugin validate` / `agy plugin list` (real binary, same
   skip-if-absent rule) against the bundle with no `hooks.json`, and separately with a
   non-firing one present, reports the plugin's skills as loaded both times. This is the
   AC's explicit regression requirement ("skills still load ... with no hooks.json ... or
   with a non-firing one present").
2. **Unit** — no Antigravity branch exists in `_tool()`/`_emit()` (i.e., the diff is
   documentation only); existing hook suite passes unmodified, same as Parity item 7.

### Data/fixtures required (either branch)

- A minimal probe bundle (`plugin.json` + `skills/` + candidate `hooks.json`) separate
  from the production `plugins/recallum-memory` tree, so `agy plugin validate` runs
  against a disposable target during automated checks and does not risk corrupting the
  real bundle under test iteration.
- A scratch `$HOME`/`XDG`-equivalent per test/run, never the developer's real `~/.gemini`.
- Fake environment fixtures for each client-var combination (extends existing pattern).

## Operational "done" for stage 8

Stage 8 returns `pass` only when:

- The Track A evidence file (transcript excerpts, probe-log excerpts, `cli.log`
  excerpts) exists in the story's directory and unambiguously shows one of the two
  falsification outcomes above — this is checked for presence and internal consistency
  (does the recorded probe-log content actually contain `DISPATCHED`/marker strings it
  claims to), not re-executed.
- Every Track B check for the branch actually taken (Parity or Gap, exclusive) passes.
- The full existing `test_plugin.py` hook-related suite passes with zero modifications
  to existing assertions (only additions).
- If Parity: `agy plugin validate` on the shipped bundle exits 0 with no schema error
  matching constraint 5's array/object message.
- If either branch ships a probe-only `agy` check and `agy` is absent from the runner,
  that check reports `blocked`, and stage 8 returns `fail`/`block` overall — it does not
  report `pass` on a skipped binary-dependent check, matching the FastMCP QA plan's rule
  that environment-skipped checks are never silently `pass`.

## Blocking dependencies

- A real `agy` v1.1.19+ binary (or matching version) for Track A entirely, and for the
  Track B integration checks (`agy plugin validate`/`list`). No mock substitutes for the
  binary in these checks — that would test the mock, not the claim.
- A TTY-capable environment (or `script`/`pexpect`) for the interactive session; this is
  unavailable in a typical headless CI runner, which is why Track A is scoped as manual
  evidence capture, not a CI gate.
- Network/model backend reachability for `agy` to actually run a turn (it is a live
  agentic CLI, not a stub) during the interactive session — an offline runner cannot
  produce Track A evidence at all.
- Isolated `$HOME`/config directories, so no credential or state from the developer's
  real Antigravity install is required or put at risk — this is a dependency the plan
  removes, not one that blocks it, but it must be honored by whoever executes Track A.

## Deliberate coverage gaps

- **No load/perf/soak test** of hook dispatch latency — out of scope; this story proves
  a boolean (fires or not), not a latency SLA.
- **No test of `agy -p`/headless hook dispatch** — already established negative by
  theme constraint 7 with its own evidence; re-proving it here is redundant. Only the
  headless-vs-interactive *contrast* is asserted qualitatively in the writeup, not
  re-tested.
- **No test of the installer or doctor writing/checking `hooks.json`** — explicitly out
  of scope per the story (S002/S003 territory).
- **No test of `mcp_config.json` runtime propagation (OQ4)** — that is a different open
  question, out of scope for this story, tracked separately in the theme.
- **No cross-client interaction test** (e.g. Antigravity + Claude Code env vars both set
  in the same process) beyond the pairwise detection-order fixtures in Track B item 2 —
  this scenario cannot occur in practice (one hook process runs under one client), so
  exhaustive combinatorial coverage would test an impossible state.
- **No test of `agy` version drift** — Track A evidence is a point-in-time fact; this
  plan does not add a CI check that re-runs the interactive experiment on every `agy`
  upgrade, since that would require the same manual/TTY dependency in a recurring gate,
  which is not currently justified by the story's scope.
