# S003 — Diagnose Antigravity CLI registration in `recallum_doctor.py`

## Actor
An operator running `recallum_doctor.py [--json]` to check the health of a Recallum installation across clients.

## Objective and motivation
The doctor already reports per-client health for Claude Code, Codex, Grok Build, and Cursor (`main()` L560-564). Antigravity has no equivalent, so a broken or missing Recallum registration for `agy` is invisible until a user's MCP tools silently fail. Add an `_antigravity` check function and wire it into the client list, following the existing `_configured_server`/`_auth_problem`/`_record_permission` helpers so redaction and permission-warning behavior stays consistent with every other client.

## In scope
- `_antigravity(home, expected, token_env, problems)` reading `~/.gemini/config/mcp_config.json` for the `recallum` entry, and (best-effort, via `agy plugin list --json` if `agy` is on `PATH`) whether the bundle is listed with `mcpServers` present.
- An entry added to the `main()` client tuple (L561-564 pattern) as `("Antigravity CLI", _antigravity(...))`.
- Checks producing `problems[]` entries for: server missing, `serverUrl` not ending exactly in `/mcp/` or using a scheme/host the existing rule rejects, missing `Authorization` header, config file mode other than `0600` (reusing `_record_permission`), and plugin not listed by `agy plugin list` when `agy` is present on `PATH`.
- Redaction of the token in `--json` output identical to existing clients' `_safe_server`/`_auth_problem` handling (no literal secret ever printed).
- Test fixtures for: no Antigravity install at all (silently absent from the report, like other absent clients), a healthy install, a world-readable config file, a missing `Authorization` header, and a wrong-path `serverUrl`.

## Out of scope
- Writing or repairing any Antigravity config file — the doctor is read-only diagnostics.
- Bundle contents or installer behavior (S001/S002).
- Hook diagnostics (S004 owns hook-specific state, if any lands).
- Docs (S005).

## Dependencies
No code dependency on S001/S002 landing: the file formats and `agy plugin list`/`agy plugin validate` JSON shapes this story checks against are already fixed by theme.md's verified constraints, so this story is buildable and testable against fixtures alone, matching the existing precedent of fixture-driven doctor checks for other clients. It should be cross-checked against S001/S002's actual output once those land, but does not require them to merge first.

## Acceptance criteria
- With no `~/.gemini` directory present in the fixture `$HOME`, the report's `clients` object contains no `"Antigravity CLI"` key (matching the "absent client is silently omitted" behavior of `_claude`/`_codex`/`_grok`/`_cursor`), and Antigravity's absence does not affect exit code.
- With a fixture `~/.gemini/config/mcp_config.json` containing a valid `recallum` `serverUrl` ending in `/mcp/`, a literal `Authorization` header, and mode `0600`, the report shows no Antigravity-related entry in `problems[]`, and exit code is `0` (assuming no other client contributes a problem).
- With the same file at mode `0644`, `problems[]` contains a permission entry naming the file path, and exit code is `1`.
- With the `Authorization` header absent, `problems[]` contains an auth entry naming Antigravity CLI, and exit code is `1`.
- With `serverUrl` set to `http://example.com/mcp/` (non-loopback plain HTTP), `problems[]` flags it, and exit code is `1`.
- `--json` output never contains the literal token value from the fixture file, in either the healthy or unhealthy fixtures.
- With a fake `agy` on `PATH` reporting the plugin listed and `mcpServers` present via `agy plugin list --json`, the report's Antigravity entry reflects `plugin_present: true`; with `agy` absent from `PATH`, the same check is skipped without raising an exception.
