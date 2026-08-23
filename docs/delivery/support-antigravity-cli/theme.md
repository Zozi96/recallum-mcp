# Theme: Support Antigravity CLI (`agy`) as a Recallum client

Status: brief for squad intake. No code written yet.
Verified against a live install: `agy` v1.1.19 at `/home/zozi/.local/bin/agy` (Linux).

## Goal

Make Recallum a first-class client of Antigravity CLI alongside Claude Code, Codex, Grok Build and
Cursor: MCP tools available, memory skills loaded, installable via `install.sh`, diagnosable via
`recallum_doctor.py`, covered by tests and documented.

Registration model (decided): **plugin bundle + native MCP**, mirroring Claude Code — the plugin
carries the skills, and the server is also written to the global MCP config so tools survive a
plugin problem.

## Verified constraints (evidence in parentheses)

1. **MCP config locations**: global `~/.gemini/config/mcp_config.json`; workspace
   `.agents/mcp_config.json`. (official docs + live file present)
2. **Remote servers must use `serverUrl`**, not `type`/`url`. Legacy shape is rejected:
   `Error: MCP server "recallum" must have either command or serverUrl`
   (`agy plugin validate` on a probe bundle). The existing `mcp.json` / `.mcp.json` are therefore
   unusable as-is; a new `mcp_config.json` is required.
   Shape: `{"mcpServers":{"recallum":{"serverUrl":"https://…/mcp/","headers":{"Authorization":"Bearer <token>"}}}}`.
   Other supported keys: `disabled`, `disabledTools`, `authProviderType`, `oauth`, and
   `command`/`args`/`env`/`cwd` for stdio.
3. **No environment-variable expansion in `mcp_config.json`.** With `RECALLUM_PROBE_TOKEN=SECRET123`
   exported, a configured header `Bearer ${RECALLUM_PROBE_TOKEN}` reached a local listener verbatim,
   unexpanded (isolated-HOME probe, `server/discover` request captured). Consequence: the API key is
   stored **literally** in `mcp_config.json`. Mandatory mitigations: write with mode `0600`, never
   commit, back up before rewrite, and have the doctor flag a world/group-readable config.
4. **Plugin bundle layout**: `plugin.json` (`{"name","description"}`; extra fields tolerated —
   the current `plugin.json` validates), plus sibling `mcp_config.json`, `hooks.json`, `skills/`,
   `agents/`, `commands/`. Install with `agy plugin install <dir>`; the CLI copies the bundle to
   `~/.gemini/config/plugins/<name>/`. `agy plugin list` prints JSON (`imports[].name`,
   `components[]`), usable by the doctor.
   Today `agy plugin validate plugins/recallum-memory` → `skills: 2 processed`, `mcpServers` and
   `hooks` "not found".
5. **`hooks.json` schema differs from Claude Code**: each event key maps to a single object, not an
   array of groups: `{"SessionStart":{"hooks":[{"type":"command","command":"…","timeout":15}]}}`
   (matcher events add `"matcher":"…"` in that same object). An array produces
   `failed to parse hooks.json: json: cannot unmarshal array into Go struct field .SessionStart`.
   Known events (binary symbols): `SessionStart`, `PreToolUse`, `PostToolUse`, `PreInvocation`,
   `PostInvocation` (proto type `SessionStartHookArgs` exists).
6. **Hook output contract is NOT Claude's.** `additionalContext` and `hookSpecificOutput` do not
   exist in the binary. Candidate output fields present: `injectSteps`, `ephemeralMessage`,
   `userMessage`, `systemMessage`, `decision`. Hook stdin fields present: `conversationId`,
   `workspacePaths`, `transcriptPath`, `artifactDirectoryPath`, `modelName`, `source`.
7. **Hooks do not fire in print/headless mode.** A valid installed plugin hook produced no dispatch
   under `agy -p` (twice) nor under `--input-format stream-json`, with no parse errors in
   `~/.gemini/antigravity-cli/cli.log`. Interactive mode was not tested (it blocks).

## Open questions the squad must close

- **OQ1** Do `SessionStart` hooks fire in interactive `agy` sessions, and what exact stdout JSON
  injects text the model sees? Until answered, hook parity is unproven. Fallback if unavailable:
  skill-only guidance (skills already load), documented as a known gap.
- **OQ2** What MCP tool-name prefix does Antigravity expose (`mcp__recallum__context` vs
  `recallum__context` vs other)? `recallum_hook.py` keeps per-client prefixes
  (`CODEX_TOOL_PREFIX`, `CLAUDE_TOOL_PREFIX`, `GROK_TOOL_PREFIX`) and the skills document tool names
  per client; an Antigravity prefix constant is needed.
- **OQ3** Which env var (if any) Antigravity exports to a hook process to identify the plugin root —
  `recallum_hook.py` detects clients via `CURSOR_PLUGIN_ROOT` / `GROK_PLUGIN_ROOT` / `PLUGIN_ROOT` /
  `CLAUDE_PLUGIN_ROOT`. Note `ANTIGRAVITY_CONVERSATION_ID` exists in the binary and may serve as the
  detection signal.
- **OQ4** Whether a plugin-carried `mcp_config.json` is actually honoured at runtime (validation
  accepts it; runtime propagation untested). This decides whether native MCP registration is a
  belt-and-braces or the only working path.

## Extension points in this repo

| Area | Anchor |
| --- | --- |
| Installer targets | `plugins/recallum-memory/scripts/install.sh`: flag parse L141, CLI detection L185-199, selection case L202-241, `install_for_codex` L580 / `install_for_claude` L994 / `install_for_grok` L1137 / `install_for_cursor` L1508, summary block L1751-1775 |
| Installer helpers to reuse | `run_action` L263, `resolve_api_key` L329, `store_env_key_files` L434, `persist_api_key` L552 |
| Doctor | `plugins/recallum-memory/scripts/recallum_doctor.py`: `_claude` L325, `_codex` L386, `_grok` L418, `_cursor` L441; client list in `main()` L561-564; helpers `_configured_server` L278, `_auth_problem` L246 |
| Hook runtime | `plugins/recallum-memory/hooks/recallum_hook.py`: client detection `_tool()` L155-200, prefixes L39-42, `_lookup_hint` L202-231, output branch `_emit` L520-533 |
| Tests | `plugins/recallum-memory/tests/test_plugin.py`: fake-CLI stdin helpers L57 (codex), L90 (cursor-agent), L123 (claude), L194 (grok); prefix assertions L1045-1048; `report["clients"][<name>]` keys L2549-2666 |
| Docs | `docs/clients.md` (title L1, "Tool surface" L7, per-client H2s L17/L55/L69/L90), `plugins/recallum-memory/skills/recallum-setup/SKILL.md` (`Setup — <Client>` H2s L43/L60/L104/L126), `plugins/recallum-memory/README.md` (L27, L65, L381 table), repo `README.md` L3/L61 |
| Client-list strings | `plugins/recallum-memory/plugin.json` L4 + keywords, `.grok-plugin/plugin-index.json` L14 and mcpServers description, `scripts/validate_external_mcp_clients.sh` |

## Proposed story split

- **S001 Bundle**: add `mcp_config.json` (serverUrl shape) at plugin root, keep `plugin.json`
  validating, confirm `agy plugin validate` reports skills + mcpServers. No installer changes.
- **S002 Installer**: `--target antigravity`, `has_agy` detection, `install_for_antigravity`
  (plugin install + merged write of `~/.gemini/config/mcp_config.json` with literal token, 0600,
  backup), inclusion in `auto`/`both` and the summary; fake-`agy` test fixture.
- **S003 Doctor**: `_antigravity(home, expected, token_env, problems)` + entry in the `main()`
  client list; checks server present, `serverUrl` exact `/mcp/`, Authorization header present,
  config mode 0600, plugin listed by `agy plugin list`.
- **S004 Hooks** (gated on OQ1/OQ2/OQ3): plugin `hooks.json` in the object schema, Antigravity
  branch in `recallum_hook.py` (detection, tool prefix, output contract), or a documented gap.
- **S005 Docs & strings**: `docs/clients.md` section, `Setup — Antigravity CLI` in recallum-setup,
  README rows and tool-name table, plugin descriptions/keywords, external-client validation script.

## Security notes

- The API key lands in cleartext in `~/.gemini/config/mcp_config.json` (constraint 3). Treat file
  mode and backup handling as acceptance criteria, not polish.
- Endpoint validation must match the existing rule: HTTPS with the exact `/mcp/` path; plain HTTP
  only for `localhost`/`127.0.0.1`.
