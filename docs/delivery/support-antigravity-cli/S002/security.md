# Security audit — S002

verdict: fail
bounce_to: 4
attempt: 1

## Findings

### F1 — MED, high confidence — `install.sh:1781` and `:1834-1835`

`umask 077` sits *inside* `if [[ -n "${resolved_api_key-}" ]]` (L1779-1784), so it is skipped whenever the key is empty — `--no-store-api-key` (L121-122) or a declined prompt (L375-377). The python child then inherits the login umask. `shutil.copyfile` (L1834) creates the backup before `os.chmod(backup, 0o600)` (L1835).

Reachable path: run 1 with a key writes a literal cleartext token; run 2 with `--no-store-api-key` sees a differing entry and backs the old file up. That backup contains the live cleartext API key and exists group/world-readable for the copy window — and stays that way **permanently** if copyfile dies mid-write (disk-full, SIGKILL), since nothing prunes backups.

Stage 5's finding that "umask 077 closes the pre-chmod window" holds only on the key-present branch.

Leader-verified independently: `umask 077` confirmed inside the conditional at L1781; backup created by `copyfile` then chmod'd at L1834-1835; host umask is `002`, so the backup is born `0664`.

Fix: hoist `umask 077` above the `if` so it is unconditional before the python child, or create the backup with `os.open(..., O_CREAT|O_EXCL, 0o600)` instead of `copyfile`. The `O_EXCL` route is stronger — it also closes the symlink-following note below.

### F2 — MED, high confidence — `install.sh:1832-1836`

Backups accumulate cleartext credentials with no pruning and no expiry. After a key rotation the `.bak-<ts>-<pid>` file still holds the previous, possibly still-valid key. The message ("Backed up the previous … (mode 600)") never tells the user the file contains a credential, so it is never deleted and is swept up by any `$HOME` backup or sync.

Retention is required by the story, so the fix is the disclosure, not the retention: state in the message that the backup holds a cleartext API key and should be deleted once the new config is verified.

## Cleared

- URL validation (L163-181): `parsed.hostname` is compared literally with no DNS, so `127.0.0.1.evil.com`, `localhost.evil.com`, `127.0.0.2` and `[::1]` all fail the loopback set and are forced to HTTPS. No cleartext-bearer bypass.
- The key never reaches argv or env: bash `printf` builtin, and the path — not the value — is passed to python3.
- `trap cleanup EXIT` (L271) verified to fire on SIGTERM, so `$tmp_dir` is removed even when `set -e` skips `rm -f -- "$key_path"`.
- `.agents/` guard (L1762-1768) is `[[ -e ]]` stat-only; the warning interpolates only the path, never contents.

## Gaps

- Defense-in-depth, not blocking: `copyfile` and `write_text` follow symlinks at the predictable `.tmp` and `.bak-<ts>-<pid>` names. Unexploitable unless `~/.gemini/config` is group-writable.
- Pre-existing, not an S002 regression: `bash -x install.sh` traces the key at L1782; the same pattern exists for Cursor at L1645.

---

# Re-audit (attempt 2) — after remediation `70d6bdd`

verdict: pass
bounce_to: none
attempt: 2

## Reasons

- **F1 closed on every path.** `umask 077` (install.sh:1783) is unconditional and precedes the `python3` fork, so `--no-store-api-key` and declined-prompt runs inherit it. It is set after `run_action agy plugin install`, and `install_for_antigravity` is the last installer called, so no other target's file modes shift. Independently, the backup's mode no longer depends on umask at all: `os.open(backup, O_WRONLY|O_CREAT|O_EXCL, 0o600)` plus `copyfileobj` (L1843-1845) makes `0600` the *birth* mode — never observable looser, never left loose on a mid-write abort. The already-matches re-run exits at the `servers.get("recallum") == entry` guard before any backup is created.
- **The `O_EXCL` collision fails safe.** `FileExistsError` propagates; `set -euo pipefail` (L2) aborts before the `.tmp` write and `tmp.replace()`, so `mcp_config.json` is untouched — no half-written config — and `trap cleanup EXIT` (L271) still removes the `$tmp_dir` holding the key file. The cost is a raw traceback, cosmetic only.
- **`O_TRUNC` on `.tmp` is the right call.** `O_EXCL` there would strand a crashed run behind a fixed filename with no recovery path; `O_NOFOLLOW` blocks the symlink redirect that actually matters. Strictly better than pre-fix, which had neither.
- **The three regression tests are genuinely red pre-fix.** The umask test asserts `config.parent.stat().st_mode & 0o077 == 0` under an injected `umask 002` — the directory is the child's surviving umask witness, deterministic rather than a race probe; pre-fix it was born `0775`. The backup test adds source assertions (`O_CREAT | os.O_EXCL, 0o600` present, `shutil.copyfile(mcp_path, backup)` absent) pinning the unobservable copy window. The F2 test asserts "cleartext", "API key" and "delete it".

## Gaps

- Non-blocking, defense-in-depth, **backlog**: `O_TRUNC` does not apply `0o600` to a pre-existing `.tmp`, and `O_NOFOLLOW` stops neither a hardlink nor an attacker-created regular file. A local user with write access to a pre-existing `0755` `~/.gemini/config/` could read the key before `os.chmod(tmp, 0o600)`. Not an S002 regression. Consider `O_EXCL`-with-unlink-retry or in-directory `mkstemp`.
- **Ruled out of scope for S002**: `bash -x install.sh` traces the key. Pre-existing and shared with the Cursor path (L1645), not introduced here. Theme-level backlog.
- No test covers `O_NOFOLLOW` on `.tmp`; behavior verified by inspection.
