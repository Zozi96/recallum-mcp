# Security audit — S005

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **No secret material committed.** The only credential strings across the seven files are placeholders (`rcl_YOUR_API_KEY`), the only URL is `https://recallum.example.com/mcp/`, and no internal hostname or key fragment appears in the diff.
- **The cleartext warning is load-bearing and correct.** `docs/clients.md` L128-133 and `skills/recallum-setup/SKILL.md` L176-180 both state the literal token, that `${RECALLUM_API_KEY}` will not expand, mode `0600`, that the retained backup also holds the key, and "never commit either one". SKILL.md L28 front-loads the warning before the install command.
- **No instruction leads to an insecure state.** Every documented path is home-scope `~/.gemini/config/mcp_config.json`. Nothing in the seven files mentions a workspace `.agents/mcp_config.json` or any repo-tracked location, so the installer's home-only guard is not undone by the docs.
- **The endpoint control is preserved verbatim** at `docs/clients.md` L135-136: HTTPS with exact `/mcp/`, plain HTTP only for `localhost`/`127.0.0.1`. No softening anywhere.
- **The stage-5 overclaim is gone.** `docs/clients.md` L143-146 and SKILL.md L195-197 now state that `skills : 2 processed` is "validation acceptance only — not evidence that skill-driven tool discovery works at runtime". A grep for runtime assertions across all seven surfaces returns only "unconfirmed" and "not evidence" phrasings.
- **Doctor guidance is safe to follow.** `recallum_doctor.py` redacts the Authorization value via `_redact_bearer`, so a user pasting doctor output into an issue does not leak the key.

## Gaps

- **Non-blocking, defense-in-depth — worth folding in later**: `docs/clients.md` L131-133 names neither the backup's filename pattern (`mcp_config.json.bak-<stamp>`) nor advises deleting it after a key rotation. The installer prints both at run time (`install.sh` L1847-1848), and the backup is created `O_EXCL` at `0600`, so the residual exposure is a revoked prior key sitting in a mode-600 home file. A reader who never runs the installer interactively would not learn the backup exists by name.
- Non-security: `plugin.json` and `plugins/recallum-memory/README.md` L7 list Antigravity CLI as a supported client without the unconfirmed-runtime qualifier that those files' own detail sections carry. Coarse product listing, not a security claim.
