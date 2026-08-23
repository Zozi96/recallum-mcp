# ADR 0019: Clients without env-var expansion are a taxonomy, not a flag

## Status
Accepted

## Context
Every client this repo configures except Antigravity expands `${VAR}` in its MCP config, so the installer writes an indirection and the secret never lands in the config file. Antigravity performs no expansion (theme constraint 3): a `${RECALLUM_API_KEY}` placeholder is transmitted to the server verbatim and can never authenticate. The API key must therefore be written literally, in cleartext, into `~/.gemini/config/mcp_config.json`.

That single property is what drove every unusual measure in S002 and S003 — they are not independent hardening choices:

- mode `0600` on the config, the tmp file, and the backup, with `umask 077` set before the `python3` child is forked so files are born private even on the paths where no key is resolved;
- a **retained** backup created with `O_CREAT|O_EXCL|0o600` rather than copy-then-chmod, because a clobbered literal token is unrecoverable whereas a clobbered `${VAR}` reference is not, and `O_EXCL` refuses a symlink pre-seeded at the predictable backup name;
- `O_NOFOLLOW` on the tmp file, for the same reason;
- global-scope writes only — the workspace-scope `.agents/mcp_config.json` is a committable path in this repository, so a cleartext key written there is one `git add` from a public commit. A pre-existing one is named in a warning and never read;
- the doctor's placeholder rejection, which must fire *regardless* of `_auth_problem`'s unset-variable outcome, because for this client a set environment variable does not make a placeholder work.

Evidence gathered after delivery raises the stakes: `agy plugin install` registers `components: ["skills"]` and does **not** write `mcp_config.json`. The installer's native write is therefore the only path that registers the server, not a redundancy — so the cleartext file is load-bearing, not belt-and-braces.

## Decision
Record "does not expand environment variables" as a client classification, and state the invariants membership imposes, rather than encoding it as a predicate or a client set in code. Any future client in this class must satisfy all five measures above; any change that weakens one of them for Antigravity is a change to this ADR, not a local edit.

## Alternatives considered
- A `CLIENTS_WITHOUT_ENV_EXPANSION` constant, or an `expands_env: bool` field on a client record: rejected; with exactly one member it is a set that reads as configuration while carrying no decision, and the five measures live in two languages across two files — no single predicate gates them.
- Fold the placeholder rejection into `_auth_problem`: rejected explicitly at S003 and reaffirmed here. Every other client's `${VAR}` is correct; sharing the check would flag four healthy configs.
- Refuse to write a key at all without expansion, and require a manual step: rejected as a product decision outside this batch's remit.

## Consequences
The literal-key path is the most dangerous write in the installer and is now the only registration path for this client. Backups accumulate cleartext keys until an operator deletes them; the installer says so on each write, and no automatic reaping exists. The doctor can detect a placeholder and a loose file mode, but cannot detect a stale or wrong literal key — only the server can. `install.sh --remote` covers the other four clients but not Antigravity (`agy` installs from a local directory or an HTTPS GitHub URL only); that gap is recorded as follow-up, outside this batch.
