## 1. Installer: native Claude MCP dual-write

- [x] 1.1 Add helpers to detect / match / write user-scoped Claude MCP server `recallum` (URL + Authorization) against `~/.claude.json` or via safe `claude mcp` APIs, without printing secrets or putting the key on argv
- [x] 1.2 Integrate into `install_for_claude` after plugin install + userConfig/credential verify: create native entry when missing; error if different without `--force-mcp`; replace when forced
- [x] 1.3 Auth rules: literal `Bearer <key>` when a key is stored this run; `Bearer ${token_env_var}` when `--no-store-api-key`; keep existing `pluginSecrets` path unchanged
- [x] 1.4 Ensure written/updated `~/.claude.json` is mode 600 when the installer mutates it; leave unrelated `mcpServers` entries intact
- [x] 1.5 Update installer usage text and post-install Claude messages: Desktop needs full quit + new session; native MCP is required for Desktop ToolSearch; shell `claude mcp list` is not a Desktop session proof

## 2. Hook and agent-facing dual prefixes

- [x] 2.1 Update `recallum_hook.py` Claude tool naming / lookup hints so Claude paths mention both `mcp__plugin_recallum-memory_recallum__*` and `mcp__recallum__*`, plus ToolSearch, without requiring both to exist
- [x] 2.2 Keep Codex / Grok / Cursor prefix behavior unchanged unless a shared helper is refactored for clarity only
- [x] 2.3 Update `recallum-memory` and `recallum-setup` skills (and `docs/clients.md` / plugin README as needed) for dual Claude prefixes and Desktop vs CLI diagnostics / false-green nested CLI checks

## 3. Tests

- [x] 3.1 Installer tests: native Claude MCP written on fresh install; matching skip; different without force fails; force rewrites URL/auth shape; no secret in command output
- [x] 3.2 Hook tests: Claude-oriented additionalContext includes dual-prefix (or native + plugin) guidance and ToolSearch; fail-open sentence retained
- [x] 3.3 Run `plugins/recallum-memory/tests/test_plugin.py` (and any focused installer dry-run) green

## 4. Version and validation

- [x] 4.1 Bump plugin patch version if shipped plugin files change (manifests + cache-facing metadata stay consistent)
- [x] 4.2 `openspec validate claude-desktop-native-mcp --strict` (or project equivalent) and plugin validate commands used in README for Claude
- [x] 4.3 Manual acceptance note in PR/summary: reinstall with `--force-mcp`, quit Claude.app, new Desktop session, ToolSearch `+recallum` or `select:mcp__recallum__context` returns tools
