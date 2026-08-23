# S002 — Add `agy` as an installer target with native MCP registration

## Actor
A Recallum operator running `plugins/recallum-memory/scripts/install.sh`; the resulting Antigravity CLI process reading `~/.gemini/config/mcp_config.json`.

## Objective and motivation
Antigravity CLI users currently have no way to get Recallum registered through the repo's installer. Add `agy` detection and an `install_for_antigravity` path mirroring `install_for_claude`'s dual-registration pattern: run `agy plugin install` for the bundle, then merge-write the native `~/.gemini/config/mcp_config.json` directly (independent of whatever the bundle carries), so MCP tools are available even if OQ4 (S001) resolves to "not honoured".

## In scope
- CLI detection: `has_agy` alongside `has_codex`/`has_claude`/`has_grok`/`has_cursor` (install.sh L185-199 pattern).
- `--target antigravity` accepted by the existing `--target` flag validation (L141), plus inclusion in `auto`. `--target both` deliberately stays codex+claude only (see Out of scope).
- `install_for_antigravity`: runs `agy plugin install <bundle dir>`, then writes/merges `~/.gemini/config/mcp_config.json` with the `serverUrl` shape from constraint 2, using the literal-token pattern (constraint 3) since Antigravity does no env-var expansion.
- File-safety handling for the native write: mode `0600` on the written file, a backup of the pre-existing file taken before any rewrite (a retained backup copy, not just an atomic tmp-swap — the token is always literal here and unrecoverable if a bad write clobbers it), and reuse of `run_action`/`resolve_api_key`/`persist_api_key` where they fit the existing pattern.
- Inclusion of Antigravity in the end-of-run summary block (L1751-1775).
- A fake-`agy` test fixture exercising `install_for_antigravity` (mirroring the fake-CLI fixtures at `test_plugin.py` L57/L90/L123/L194).

## Out of scope
- Changes to the bundle's `mcp_config.json` contents (S001).
- Doctor changes (S003).
- Hook runtime changes (S004).
- Docs/strings changes (S005).
- Any interactive fallback UI beyond the existing flag-driven install flow.
- Widening `--target both` to include Antigravity: `both` is codex+claude and hard-fails if either is absent (install.sh L236-247); Grok and Cursor were never added to it either, so extending it here would newly require `agy` for every existing `--target both` invocation and break users without it.
- Workspace-scope `.agents/mcp_config.json` registration (the second location named in constraint 1). The decided model for this theme is plugin bundle (S001) plus global native MCP (this story) — mirroring Claude Code, which likewise has no workspace-scope write path in this installer. This story does not add one for Antigravity. This exclusion carries a live risk the installer must actively guard against, not merely decline to build: `.agents/` already exists in this repo, is not gitignored, and constraint 3 means any `mcp_config.json` written there would carry the API key in cleartext into a tracked, committable path. See the positive guard in the acceptance criteria below.

## Dependencies
No hard dependency on S001: `install_for_antigravity`'s native write is a self-contained file operation, not a read of the bundle's `mcp_config.json`, so this story is deliverable and testable whether or not S001 has landed. It shares OQ4 evidence with S001 — if S001's probe finds the bundle config IS honoured, this story's native write becomes belt-and-braces (matching the Claude Code model); if not, it is the only working MCP path. Either way this story's acceptance criteria hold unchanged, since they only assert facts about the native file this story writes.

## Acceptance criteria
- With a fake `agy` on `PATH`, `./install.sh --target antigravity` calls `agy plugin install` with the bundle path and then writes `~/.gemini/config/mcp_config.json` (under the fixture's fake `$HOME`) containing `mcpServers.recallum.serverUrl` ending exactly in `/mcp/` and an `Authorization` header.
- Without `agy` on `PATH`, `./install.sh --target antigravity` exits non-zero with an error naming `agy` as missing, and writes nothing.
- `./install.sh --target auto` includes Antigravity in the actions it takes when (and only when) `agy` is detected on `PATH`, without requiring `--target antigravity` explicitly.
- The written `mcp_config.json` file has mode `0600` after the run.
- When a pre-existing `~/.gemini/config/mcp_config.json` is present before the run, a backup copy of its prior contents exists on disk after the run, distinct from the new file.
- A URL failing the existing validation rule (non-HTTPS non-loopback, or a path other than `/mcp`/`/mcp/`) is rejected before any file is written, matching the rule already enforced for other clients (L163-181).
- Re-running the install with an unchanged target `mcpServers.recallum` entry does not report a diff/change (idempotent on unchanged input), matching the `matching`-state pattern used for Claude Code.
- The end-of-run summary output includes an Antigravity line when the target was installed.
- `git status` after the test run shows no tracked repository file modified — the fixture never touches a real `~/.gemini` path outside the test's own fake `$HOME`.
- `install_for_antigravity` never writes to any path under `.agents/` (workspace-scope), in the current working directory or elsewhere in the repository tree, under any `--target`/flag combination this story implements; a test asserting `.agents/mcp_config.json` does not exist after every installer invocation covered by this story's fixtures passes.
- If a `.agents/mcp_config.json` already exists in the current working directory before the run (simulating a prior manual or third-party write), the installer does not modify, delete, or read secret values from it, and emits a warning naming the file as a workspace-scope config outside this story's supported registration path.
