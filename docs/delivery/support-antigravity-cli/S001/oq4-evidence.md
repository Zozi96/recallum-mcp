# OQ4 probe evidence — S001

## Outcome

**BLOCKED** (not honoured / not honoured / inconclusive — none recorded).

This is deliberately not "inconclusive" as a story outcome. The story's AC3(c)
sets an evidence bar for "inconclusive": at least one genuine interactive-mode
attempt, a transcript, and a named technical blocker. This agent could not
complete that attempt far enough to observe the running CLI's active MCP
servers at all — the attempt was stopped by an earlier gate (sign-in), not by
reaching and failing at the MCP-listing surface. Recording "inconclusive"
would overstate what was actually tried. The honest state is: this needs a
human at a real terminal with a Google account to get past sign-in and
finish the probe.

## What was attempted (transcript)

All commands ran with an isolated `HOME` (`$(mktemp -d)`), never the
operator's real `$HOME`/`~/.gemini/`.

1. **Isolation check.**
   `HOME=$QA_HOME agy plugin list` → `No imported plugins.` Confirms
   `$QA_HOME/.gemini` started empty, per the QA plan's step 1.

2. **Bundle install, no native config.**
   `HOME=$QA_HOME agy plugin install plugins/recallum-memory` from repo root
   → exit 0, printed `skills: 2 processed`, `mcpServers: 1 processed`.
   `test ! -f "$QA_HOME/.gemini/config/mcp_config.json"` → confirmed absent
   (no native registration present). The bundle's `mcp_config.json` was
   copied verbatim to
   `$QA_HOME/.gemini/config/plugins/recallum-memory/mcp_config.json`.

3. **Genuine interactive-mode attempt.**
   Launched `HOME=$QA_HOME agy` (no `-p`, no `--input-format stream-json`)
   inside a real pty via `tmux new-session -d -s oq4probe "HOME=$QA_HOME agy"`
   — a true interactive terminal session, not headless/print mode. Captured
   with `tmux capture-pane`. Output:

   ```
   Welcome to the Antigravity CLI. You are currently not signed in.

   Select login method:
   > 1. Google OAuth
     2. Use a Google Cloud project
   ```

   Selected option 1 (`tmux send-keys "1" Enter`). Output advanced to:

   ```
   Open the URL below in your browser:
   https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=...
   (Google OAuth authorization URL, full scope list, PKCE challenge, state)

   After authenticating, copy the code displayed in the browser and paste it
   below:
   authorization code...
   ```

   No further command was sent past this point.

## Named technical blocker

Interactive `agy` requires completing a Google OAuth device-code flow (or a
GCP project login) before any session — and therefore any in-session MCP
server listing surface — becomes reachable. Completing it requires a human
opening the printed URL in a real browser, authenticating with a Google
account, and pasting back an authorization code. This agent has no browser
and no Google account credentials to supply, and the isolated `HOME` used for
this probe deliberately starts with zero cached credentials (per the
isolation contract in the QA plan — reusing the operator's real
`~/.gemini/` credentials would defeat the "bundle alone, no native config"
precondition the OQ4 finding depends on, and would risk mutating real state).
There is no non-interactive/headless substitute for this login step that was
found, and the QA plan's own evidence bar (theme.md constraint 7 discussion,
non-blocking wording defect aside) already anticipates that this class of
check needs a human-operated terminal.

Consequence: whether `recallum` appears among "active MCP servers" once
signed in was never reached and was not observed either way.

## Escalation

This blocks S001 AC3 (the OQ4 probe requirement) on a human prerequisite:
a person with a Google account, a browser, and a real interactive terminal
must run steps 1-2 above (already scripted and verified reproducible) and
then complete sign-in inside the `tmux`/interactive `agy` session (or a plain
terminal) to reach an in-session command that lists active MCP servers
(discoverable via `/help` inside the session, per the QA plan's procedure),
and record honoured / not honoured / inconclusive with that evidence.

## Isolation and cleanup

- `$QA_HOME` was a fresh `mktemp -d`, never the operator's `$HOME`.
- `tmux kill-server` and `rm -rf "$QA_HOME"` were run after the attempt.
- `git status --porcelain` at repo root after cleanup shows no changes
  outside this story's diff (`plugins/recallum-memory/mcp_config.json`,
  `plugins/recallum-memory/tests/test_plugin.py`, and this file) — the
  operator's real `~/.gemini/` was never touched.
