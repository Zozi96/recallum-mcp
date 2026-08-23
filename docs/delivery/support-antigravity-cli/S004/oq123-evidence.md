# S004 — OQ1/OQ2/OQ3 evidence

Status: **BLOCKED**. Neither fork branch may be recorded.

## Why neither outcome can be recorded

S004's story permits exactly two outcomes, Parity or Gap, and both require observation
in a live interactive `agy` session:

- **Parity** needs the hook to dispatch, the stdin fields observed, and injected content
  confirmed to reach the model's context.
- **Gap** needs *no dispatch observed after a genuine interactive attempt*.

The blocker stops us before either observation is possible. A prior agent on this theme made
a genuine interactive attempt — isolated `HOME`, `tmux` pty, no `-p` — and `agy` presented a
**Google OAuth sign-in gate before any session, hook dispatch, or MCP listing surface was
reachable**. Full transcript in `../S001/oq4-evidence.md`.

Being stopped at sign-in is **"cannot tell"**, not "no dispatch observed". Recording the Gap
branch from this evidence would misstate what was seen, which is exactly what the story's
evidence bar exists to prevent. Hence `blocked`.

Theme constraint 7 independently established that hooks do not fire under `agy -p` or
`--input-format stream-json`, so there is no headless substitute for the observation.

## What WAS established without an interactive session

- `plugins/recallum-memory/hooks.json` in the Antigravity single-object event schema is
  accepted: `agy plugin validate plugins/recallum-memory` reports `hooks : 1 processed`,
  with `skills : 2 processed` and `mcpServers : 1 processed` unchanged.
- The hook command resolves the plugin root from `PLUGIN_ROOT` / `GROK_PLUGIN_ROOT` /
  `CLAUDE_PLUGIN_ROOT` and, when none resolves, consumes stdin and exits 0 harmlessly.
  OQ3 is unresolved, so no new Antigravity-specific variable was invented — a wrong constant
  that silently never matches would be worse than none.
- `recallum_hook.py` was deliberately NOT given an Antigravity branch: OQ2 (the tool-name
  prefix) is unresolved, and guessing it would ship a constant that never matches.
- Real `agy` v1.1.19 facts confirmed: `agy plugin list --json` prints `No imported plugins.`
  (plain text, exit 0) when empty; after install it returns JSON with
  `imports[].name = "recallum-memory"` and `components: ["skills","mcpServers"]`.

## Open risk this creates — needs a decision before the branch is merged

Shipping `hooks.json` flips `agy plugin validate` from `hooks : skipped (not found)` to
`hooks : 1 processed`. If the hook never actually fires, that line tells a user hook parity
works when it may not. A green indicator that lies is worse than an absent one.

Options: hold `hooks.json` until OQ1 is answered; or ship it with an explicit doc note in
S005 stating that validation acceptance is not evidence of dispatch. **Not decided here.**

## What unblocks this

A human with a browser and a Google account, completing sign-in in an interactive `agy`
session, then observing whether a `SessionStart` hook dispatches — and if it does, which of
`injectSteps` / `ephemeralMessage` / `userMessage` / `systemMessage` / `decision` injects
model-visible text (OQ1), what tool-name prefix the MCP tools appear under (OQ2), and which
environment variable identifies the plugin root (OQ3).
