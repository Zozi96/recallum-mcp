# Code review — S003

verdict: pass
bounce_to: none
attempt: 1
senior_implementer: false

## Reasons

- Shared helpers are behavior-preserving. `_record_permission` with `client=None` yields `label=""`, reproducing the pre-existing message byte-for-byte (recallum_doctor.py:249-250). `_safe_server` default `url_key="url"` leaves callers L350/L437/L457/L486 unchanged; only the new L588/L592 Antigravity call sites pass the new arguments. Sibling doctor tests green.
- The `agy` skip is genuine, not a mask. `_antigravity_plugin_present` returns None on a `shutil.which` miss and on `_run_json` returning None (nonzero exit, malformed JSON, OSError/timeout, L185-203), appending no problem and omitting `plugin_present`, while config/auth/permission/endpoint checks still run. All three modes tested with returncode 0 and no traceback.
- Permission checks: `0644` and `0640` both flagged. The umask test is sound — `path.chmod(mode)` after write is umask-immune, and the test asserts `file_mode == "0644"` under `os.umask(0o077)`, proving the planted file is genuinely loose.
- Redaction assertions are non-vacuous: token planted in config, `assertNotIn(token)` and `assertNotIn(token[4:])` across text and JSON; the healthy test's `"Bearer *** (literal)"` assertion proves the auth line is emitted, so a redaction break would trip the NotIn.
- Endpoint rule does not fork a drifting copy: no prior Python copy existed (`_safe_url` is redaction only), the shell rule (install.sh:174-181) cannot be imported, and the doctor's exact-`/mcp/` matches install.sh's post-normalization invariant (`/mcp` normalized to `/mcp/` at write time, L179-181).
- Test isolation holds: `_run_doctor` fully replaces PATH (`home/bin:/usr/bin:/bin`, test_plugin.py:2436), so the real `agy` at `/home/zozi/.local/bin/agy` is unreachable; `FAKE_AGY_SENTINEL_v1` asserted in both agy-consulting tests.
- `_expected` unused-in-signature follows a real precedent: `_auth_problem`'s `_token_env` (recallum_doctor.py:254-256) is unused for uniform call sites with the same documented rationale.

## Evidence

- Leader-verified independently: full suite `148 passed, 78 subtests passed` (baseline on main 142/76); `-k Antigravity` → 14 passed, 7 subtests; `-k "doctor and not Antigravity"` → 14 passed, 8 subtests.
- `git status --porcelain` in the worktree shows only `recallum_doctor.py` and `test_plugin.py` modified.
- Worktree: `.claude/worktrees/agent-a1cf8e6ff3d7dec66`, branch `worktree-agent-a1cf8e6ff3d7dec66`.

## Gaps

- Non-blocking: endpoint tests omit a `localhost`-hostname case; only `127.0.0.1` is covered.
- Non-blocking: the malformed-JSON and nonzero-exit `agy` tests do not assert the sentinel log, so they would pass vacuously if the fake fell off PATH. Mitigated by the two sentinel-asserted tests.
