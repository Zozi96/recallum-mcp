# Code review — S002

verdict: pass
bounce_to: none
attempt: 1
senior_implementer: true
senior_trigger: writes a cleartext authentication credential to disk; crosses a module boundary (installer target + native config write)

## Reasons

- **Ruling on `--target both`: deviation accepted; `story.md` L11 is a spec defect.** `install.sh` L236-247 shows `both` hard-fails when either CLI is absent, so adding antigravity would break every existing `both` user without `agy`. Grok and Cursor set the precedent — neither was ever added to `both`, and help text L13 documents it. `test_both_stays_codex_and_claude_only` pins the behavior non-vacuously: agy is stubbed present, and the test asserts no agy call and no config file.
- Credential safety verified end to end: final file `0600` (asserted), tmp `0600` before rename, retained backup `bak-<ts>-<pid>` chmod `0600` and asserted `0600` in test. `umask 077` inherited by the python child closes the pre-chmod window. Merge preserves unrelated `mcpServers` and top-level keys (tested). Idempotent re-run accumulates no secret backups (tested). The key is passed via a `0600` temp file under a trap-cleaned `$tmp_dir`, never through argv or env of the fake CLI.
- `.agents/` guard is stat-only (`[[ -e ]]`) with no write path in existence. The poisoned-fixture test is genuinely non-vacuous: malformed JSON plus a NUL byte would crash any parse; exit status, stdout and stderr are compared against the file-absent baseline; bytes and mode unchanged; `DECOY-DO-NOT-USE` absent from all streams and from `FAKE_CLI_LOG`.
- The one modified pre-existing test (`test_auto_target_fails_when_no_cli_is_present`) was forced by the new error string at install.sh L214; assertion strength is unchanged.
- Test isolation holds: `PATH` is fixture-bin plus `/usr/bin:/bin` (test_plugin.py L1317), excluding `~/.local/bin`; `HOME` overridden; `FAKE_AGY_SENTINEL` guards against silent reachability of the real binary.

## Evidence

- Reviewer ran the full suite: **149 passed, 77 subtests** against a main baseline of **134** — the +15 are exactly the 15 new tests.
- Leak grep over captured pytest output for `SENTINEL-NOT-A-REAL-KEY` and `DECOY-DO-NOT-USE`: 0 matches.
- Worktree `.claude/worktrees/agent-aca443c21a0f75922`, branch `worktree-agent-aca443c21a0f75922`.

## Gaps

- **Spec defect to correct**: `story.md` L11 requires inclusion in `both`; that criterion is wrong and must be amended, or stage 8 will fail S002 for honouring the correct behavior.
- Non-blocking: usage text L13 "(not Grok/Cursor)" does not yet name Antigravity — one-line polish S005 can absorb.
- Accepted from the worker: env-key files unasserted for an antigravity-only target (inert without env expansion); real `agy` runtime honouring unverified — that is S001's OQ4, currently blocked.
