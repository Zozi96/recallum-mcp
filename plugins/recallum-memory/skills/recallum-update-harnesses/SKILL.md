---
name: recallum-update-harnesses
description: Updates the Recallum plugin on every installed harness after a plugin version bump. Use when the user asks to update harnesses, refresh client plugins, sync Codex/Claude/.agents/Grok/Cursor/Devin/Antigravity/Muse to a new recallum-memory version, or fix VERSION DRIFT from recallum_doctor.
---

# Recallum Update Harnesses

Refresh already-installed plugin copies so they match this checkout's
`plugins/recallum-memory/plugin.json` version. First-time install is
`scripts/install.sh`, not this skill.

Never print, echo, interpolate, or store an API key in chat. Do not `cat`,
`head`, `grep`, or parse `~/.cursor/mcp.json`, `~/.claude/.credentials.json`,
`~/.claude.json`, `~/.config/recallum/env`, `~/.grok/config.toml`, or any
plugin-cache `mcp.json`.

Tool prefixes (for new-session checks only): Codex `mcp__recallum__`, Claude
Code plugin `mcp__plugin_recallum-memory_recallum__`, Claude native/Desktop
`mcp__recallum__`, Grok `recallum__` via `search_tool` / `use_tool`, Cursor
Available Tools (no stable prefix), Devin `mcp__recallum__`, Muse Code
`mcp__recallum__`.

## 1. Baseline

From the recallum-mcp checkout:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py --json
```

Record `repo_version` and every `VERSION DRIFT` line. Detect CLIs with
`command -v` for `codex`, `claude`, `grok`, `agent`/`cursor-agent`, `devin`,
`agy`, `muse`. Skip a client that is not installed.

`PLUGIN` below is `<repo>/plugins/recallum-memory`. Repo marketplace name is
`recallum-local`.

## 2. Update each present client

Do not use `install.sh --target auto` as the updater: it skips already-installed
plugins unless `--force-mcp`, and `--force-mcp` rewrites MCP configs. Prefer the
per-client commands. Leave working MCP URLs alone.

### Codex (`.agents` marketplace)

Local marketplace cannot `codex plugin marketplace upgrade` (not a Git source).
Reinstall the plugin from disk:

```bash
codex plugin remove recallum-memory@recallum-local
codex plugin add recallum-memory@recallum-local
codex plugin list
```

Expect `recallum-memory@recallum-local` at `repo_version`.

### Claude Code

If the plugin is missing, `install.sh --target claude` (stores the key from the
environment or a hidden prompt; never `--config api_token=...`). If it is
already installed and only the cache is stale:

```bash
plugins/recallum-memory/scripts/install.sh --target claude --force-mcp
```

`--no-store-api-key` after a reinstall leaves tool calls unauthenticated when
`pluginSecrets` was cleared. Re-run without that flag so the existing
`RECALLUM_API_KEY` is persisted (value not printed). Confirm
`recallum-memory@recallum-local` at `repo_version` via `claude plugin list --json`.

### Grok Build

`grok plugin update` is a no-op for a local-path install ("already live").
Uninstall, then install the directory:

```bash
grok plugin uninstall recallum-memory
grok plugin install "$PLUGIN" --trust
grok plugin enable recallum-memory
```

`grok plugin install` alone fails with "already installed" (dedup by
`repo_key`). Confirm version in `grok plugin list --json`.

### Cursor

The CLI cannot install or bump the plugin. Re-index the GitHub marketplace
(plain `update` can leave a stale `git_head`):

```bash
agent plugin marketplace remove recallum-local
agent plugin marketplace add https://github.com/Zozi96/recallum-mcp
```

Then tell the user: Settings → Plugins → marketplace `recallum-local` →
update/enable `recallum-memory`, then **fully quit and reopen** Cursor. Doctor
`plugin_cache` stays old until they do that.

Do not rewrite `~/.cursor/mcp.json` unless MCP itself is broken.

### Devin CLI

Two copies can coexist (GitHub personal plugin vs `--local` checkout). Update
both to `repo_version`:

```bash
devin plugins update recallum-mcp#plugins/recallum-memory
devin plugins install --local "$PLUGIN" -y
devin plugins list
```

Org-policy timeouts on `update` are not fatal; the `--local` install still
lands. Do not `remove --local` a cloud personal plugin (that command fails);
omit `--local` only if the user asked to drop the cloud copy.

### Antigravity CLI (`agy`)

```bash
agy plugin uninstall recallum-memory
agy plugin install "$PLUGIN"
agy plugin validate "$PLUGIN"
```

Expect `skills : 2 processed`. Hooks reporting
`1 processed` is validation only, not dispatch.

### Muse Code (`muse`)

```bash
muse plugins update recallum-memory
muse plugins approve plugin:recallum-memory:hook:session-start
muse plugins approve plugin:recallum-memory:hook:user-prompt-submit
muse plugins hook test plugin:recallum-memory:hook:session-start \
  --fixture '{"event": "SessionStart", "stdin": {"cwd": "$PWD"}}'
```

The update changes the hook definition hashes, so both hooks go inactive until
re-approved — the approve calls are not optional. Do not rewrite
`settings.json` unless MCP itself is broken. Confirm version in
`muse plugins list --json`.

## 3. Verify

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
```

Healthy means every installed plugin version equals `repo_version`, except
Cursor `plugin_cache` until the user updates in the UI. Report remaining drift
per client; do not claim Cursor is updated from marketplace re-index alone.

Tell the user to start a **new** session on each updated CLI. Claude Desktop:
fully quit the app, then ToolSearch `+recallum` — nested `claude mcp list` is
not Desktop proof.
