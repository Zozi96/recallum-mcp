# QA report — S005

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **All seven acceptance criteria met.** `docs/clients.md` L111-181 carries the Antigravity H2 with the exact `--target antigravity` command, the `~/.gemini/config/mcp_config.json` path and the literal-token security note. SKILL.md L160-200 has a step-by-step `Setup — Antigravity CLI` with no undocumented prerequisites. The tool prefix is stated as "not yet determined — no prefix constant exists" in `docs/clients.md` L179, SKILL.md L200/223 and the plugin README L399 — named, never invented, never omitted. Root `README.md` L4/L62 includes Antigravity in the client list. `plugin.json` L4/L19 and `.grok-plugin/plugin-index.json` L14/L30 mention it. `validate_external_mcp_clients.sh` L9 includes Antigravity CLI.
- **The cleartext-key warning reaches a reader in full** (`docs/clients.md` L128-133): literal bearer token, `${VAR}` will not expand for Antigravity, mode `0600`, the backup also holds the key in cleartext, and "do not commit them."
- **Install facts are accurate** (`docs/clients.md` L119-126): `--target antigravity`; local directory or HTTPS URL, not `git@…` and not `owner/repo` shorthand; `--remote` does not cover antigravity; `--target both` stays codex+claude. All match the leader's probe of the real `agy` v1.1.19.
- **No runtime overclaim survives.** The hooks and skills prose (L163-172) hedges consistently — "not evidence", "unconfirmed", "expected but unconfirmed" — matching S004's blocked status. A sweep for `works today` / `load at runtime` / `hooks work` across all four prose surfaces returns no matches.
- **Stage-7 gap ruled non-blocking, and the reasoning holds**: the backup is created `O_EXCL` at `0600` (install.sh L1837-1843), scoped to the file owner. A reader who never runs the installer never has a backup file to encounter, and anyone who does run it sees the installer's own printed filename and delete-advice at creation time (L1846-1849). Defense-in-depth, not a live exposure.
- Grok Build's pre-existing omission from `validate_external_mcp_clients.sh` confirmed left as-is per the explicit scope decision — not silently fixed.

## Evidence

- Leader-verified: the QA plan's grep loop over the 7-surface inventory returns 13 / 15 / 4 / 2 / 2 / 2 / 1 Antigravity mentions. Suite 176 passed, 90 subtests; ruff clean.

## Gaps

- None blocking.
