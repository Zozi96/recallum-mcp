# QA report — S002

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- Full suite **176 passed, 90 subtests** (main baseline 134); 42 Antigravity-scoped tests pass individually; the sibling-CLI subset (codex/cursor/grok/claude) is unregressed at 77 passed.
- `git status --porcelain` identical before and after the run — no tracked file touched, confirming the no-workspace-write claim.
- **Cleartext credential handling.** `test_written_config_is_private` (final file `0600`), `test_pre_existing_config_is_backed_up_before_being_rewritten` (backup `0600`, distinct content), plus `test_no_store_api_key_path_does_not_leak_the_login_umask` and `test_backup_of_a_stored_key_is_private_on_the_no_store_path`, which set `umask 002` and assert file and directory modes. These genuinely fail under the pre-fix scoped `umask 077`. The last also greps the installer source for `os.O_CREAT | os.O_EXCL, 0o600` and asserts the absence of `shutil.copyfile(mcp_path, backup)`, pinning the fix in code rather than only in behavior. `test_merge_preserves_unrelated_servers` confirms merge fidelity. Sentinel and decoy grep over full captured output: 0 hits.
- **`.agents/` guard.** `test_no_workspace_scope_config_is_ever_created` proves no write across three flag combinations. `test_pre_existing_workspace_config_is_neither_read_nor_touched` uses a poisoned malformed decoy: the file is byte-identical afterwards, its mode unchanged, stdout and stderr match the file-absent baseline apart from one warning block, and the decoy string appears in no stream. That is genuine proof of non-reading — a real parse would crash on the malformed trailing bytes or echo the decoy — not an assertion of convenience.
- **Endpoint rule** proven both ways: `test_invalid_urls_are_rejected_before_any_file_is_written` (non-HTTPS, wrong path) and `test_loopback_http_url_is_accepted` (plain HTTP on `127.0.0.1`).
- The one modified pre-existing test, `test_auto_target_fails_when_no_cli_is_present`, asserts the full literal string including `agy`. Necessary because of the new target, and not weakened.
- **Coverage honesty.** `qa-plan.md`'s "Not automatable" section explicitly declares real-`agy` compatibility and OQ4 runtime honouring as manual or blocked, not silently skipped. `skipUnless(AGY, ...)` appears only in pre-existing S001 tests, unrelated to S002's `AntigravityInstallTests`.

## Evidence

- Leader-verified independently: full suite 176/90, sibling subset 77 passed, `bash -n` OK, credential-sentinel grep over the tree 0 hits.

## Gaps

- None blocking.
- Carried to backlog from stage 7: `O_TRUNC` does not reapply `0600` to a pre-existing `.tmp`, and `O_NOFOLLOW` stops neither a hardlink nor an attacker-created regular file. Exploitable only if `~/.gemini/config/` is already group-writable. Not an S002 regression.
