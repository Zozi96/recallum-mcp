# S004 — OQ1/OQ2/OQ3 evidence

Status: **GAP branch, evidenced.** Hooks do not dispatch. OQ2 and OQ3 are moot for this story.

## Why earlier attempts were inconclusive, and what was wrong with them

Every earlier probe used `HOME=$(mktemp -d)`, which creates a virgin **unauthenticated** profile,
so `agy` stopped at a Google OAuth sign-in gate before any session existed. That was reported as
an environmental blocker needing a human. It was an artifact of the isolation choice: the real
profile at `~/.gemini/` is authenticated (`antigravity-cli/antigravity-oauth-token`) and `agy -p`
answers with exit 0 and no prompt.

## Method

Against the authenticated profile, fully reversible. The bundle was installed, its installed
`hooks.json` temporarily replaced with a probe that appends `DISPATCHED`, the hook's stdin, and a
filtered `env` dump to a file — so dispatch is proven independently of whether any output field
renders. The original was restored and the plugin uninstalled afterwards.

The probe `hooks.json` used the Antigravity single-object event schema and was accepted:
`agy plugin validate` → `hooks : 1 processed`.

## Result — OQ1: no dispatch, in either mode

```
print mode
  $ agy -p "reply with the word: probe"
  probe                                   ← model answered, so a turn ran
  probe file: absent                      ← NO DISPATCH

interactive mode, via a pty (script -qec), authenticated
  $ script -qec "agy -i 'reply with the word probe then exit'"
  TUI initialised; conversation created ("Resume with -c (or command below):")
  probe file: absent                      ← NO DISPATCH

~/.gemini/antigravity-cli/cli.log
  no hook entries at all — no dispatch record AND no parse error,
  so the hooks.json was valid and simply never invoked
```

A session genuinely existed in the interactive run — the TUI initialised and a resumable
conversation was created — and the `SessionStart` hook still did not fire.

This meets the story's Gap evidence bar: no dispatch observed after a genuine interactive
attempt, in an authenticated profile, with a valid installed `hooks.json`.

Theme constraint 7 is therefore **confirmed rather than superseded**: it reported that hooks do
not fire under `agy -p`, and that holds even once authentication is not a factor.

## OQ2 and OQ3 — moot for this story

- **OQ3** (which env var identifies the plugin root) can only be answered from inside a running
  hook process. No hook process is ever created, so there is nothing to observe.
- **OQ2** (the MCP tool-name prefix) requires recallum's MCP tools to be loaded. Per S001's OQ4
  result, the bundle config is not honoured at runtime, so that needs a native config entry with
  a **real API key** — out of scope here, and not something to do without the owner's say-so.

Neither is needed for the Gap branch: with no hook process, `recallum_hook.py` needs no
Antigravity detection branch and no tool-prefix constant. The absence of both is now the
correct implementation, not an omission.

## Consequence for the shipped `hooks.json`

The bundle's `hooks.json` validates (`hooks : 1 processed`) but is inert. It should either be
withdrawn, or kept with the documentation stating plainly — as `docs/clients.md` now does — that
validation acceptance is not dispatch evidence. **This is a decision for the repository owner.**

## Constraint 5 is unverified at the reachable layers

Theme constraint 5 claims a Claude-style array-of-groups `SessionStart` (`{"SessionStart":[{"hooks":[...]}]}`)
is rejected by `agy plugin validate`/`install` with
`failed to parse hooks.json: json: cannot unmarshal array into Go struct field .SessionStart`.
Re-tested directly against real `agy` v1.1.19 (isolated `HOME=$(mktemp -d)`, unauthenticated —
sufficient for `plugin validate`/`install`, which do not require a session) with a minimal probe
bundle:

```
hooks.json = {"SessionStart":[{"hooks":[{"type":"command","command":"true","timeout":15}]}]}   (array)
  $ agy plugin validate <probe>
  hooks : 1 processed        ← ACCEPTED, no parse error

hooks.json = {"SessionStart":{"hooks":[{"type":"command","command":"true","timeout":15}]}}     (object, ours)
  $ agy plugin install <dir>  (isolated HOME)
  hooks : 1 processed        ← ACCEPTED
```

Both schema forms are accepted by both `plugin validate` and `plugin install`; `cannot unmarshal`
never appears at either layer. Whatever produces the Go unmarshal error, if it exists at all, is
not observable from `validate`/`install` — it could only be the runtime hook-loading path at
session start, which per OQ1 above is never reached. This is the same class of error as the
OAuth-wall artifact: a claim recorded from an isolation choice (validate/install only, no
interactive dispatch) that does not hold up to direct re-verification. It changes nothing about
the story's outcome — the Gap branch already does not depend on constraint 5 — but the theme brief
should not be treated as settled fact for this constraint without a runtime reproduction.

## Environment restored

Original `hooks.json` restored, plugin uninstalled, native config diffed identical to its
pre-experiment snapshot, temporary files removed.
