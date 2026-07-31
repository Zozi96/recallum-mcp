<p align="center">
  <img src="assets/logo.svg" alt="Recallum" width="132" height="132" />
</p>

# Recallum Memory plugin

Durable, project-aware memory for **Grok Build**, **Codex**, and **Claude Code**, backed by a
self-hosted Recallum MCP server.

The plugin ships:

- two skills — `recallum-memory` (load context and capture verified reusable knowledge) and
  `recallum-setup` (install and diagnose);
- two hooks — `SessionStart` injects the canonical project key and a completion capture reminder;
  `UserPromptSubmit` nudges recall when a prompt mentions memory. Both fail open;
- the MCP wiring for each client.

One plugin package, three native entry points — not a Claude-only addon:

| Client | Marketplace index | Plugin metadata |
| --- | --- | --- |
| Grok Build | `.grok-plugin/marketplace.json` | `plugin.json` |
| Codex | `.agents/plugins/marketplace.json` | `.codex-plugin/plugin.json` |
| Claude Code | `.claude-plugin/marketplace.json` | `.claude-plugin/plugin.json` |

## Grok only (no Claude Code)

You do **not** need Claude Code installed, configured, or on `PATH`. Grok discovers this plugin
from its own marketplace and registers the MCP server in `~/.grok/config.toml`.

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY

# From a checkout of this repo:
plugins/recallum-memory/scripts/install.sh --target grok --url https://recallum.example.com/mcp/

# Or tracking the published repository (no local checkout after install):
plugins/recallum-memory/scripts/install.sh --target grok --remote --url https://recallum.example.com/mcp/
```

Equivalent manual steps:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY

grok plugin marketplace add Zozi96/recallum-mcp   # or: path/to/this/repo
grok plugin install recallum-memory --trust
grok plugin enable recallum-memory

grok mcp add --transport http recallum https://recallum.example.com/mcp/ \
  --header "Authorization: Bearer \${RECALLUM_API_KEY}"

grok mcp doctor recallum    # handshake OK, tools discovered
```

Why the MCP step is separate: Grok does not resolve Claude-style `${user_config.*}` in
`.mcp.json`. The installer (and the `mcp add` above) write a real URL plus
`Bearer ${RECALLUM_API_KEY}` into config.toml. That entry takes precedence over any unresolved
plugin placeholder with the same server name.

After install, start a **new** Grok session. Tools appear as `recallum__*` via `search_tool` /
`use_tool`.

## Prerequisites

- A reachable Recallum server, yours. The endpoint must be HTTPS and its path must end in `/mcp`
  or `/mcp/`. Plain HTTP is accepted only for `localhost` / `127.0.0.1`. `scripts/install.sh`
  defaults to `https://recallum.zozbit.com/mcp/`; enabling the plugin from the marketplace has no
  default and prompts for the endpoint, so nobody ends up pointed at another operator's server by
  inheriting a value they never chose.
- `python3` on `PATH` — the hooks run under it. Any 3.9+ interpreter works.
- The `codex`, `claude`, and/or `grok` CLI.

## Install

Run from anywhere; the script resolves the repository root from its own location.

```bash
plugins/recallum-memory/scripts/install.sh
```

With no `--target`, it installs into **every CLI it detects**. Preview first with `--dry-run`,
which prints the exact commands and mutates nothing:

```bash
plugins/recallum-memory/scripts/install.sh --dry-run
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--url URL` | `https://recallum.zozbit.com/mcp/` | Recallum MCP endpoint |
| `--target TARGET` | `auto` | `auto`, `codex`, `claude`, `grok`, or `both`. `auto` uses every detected CLI; `both` is Codex + Claude Code only; explicit targets fail if that CLI is missing |
| `--token-env-var NAME` | `RECALLUM_API_KEY` | Environment variable Codex and Grok read the bearer token from. Claude Code always checks `RECALLUM_API_KEY` |
| `--claude-scope SCOPE` | `user` | **Claude Code only.** `user`, `project`, or `local`; applied to the marketplace and the plugin install |
| `--remote` | off | Register the private GitHub repository instead of this local checkout |
| `--force-mcp` | off | Replace an existing setup: a differing Codex/Grok MCP definition, or an already-installed Claude Code plugin |
| `--dry-run` | off | Validate and print the plan without mutating anything |
| `--help` | | Usage |

The script validates the URL and the marketplace manifests for the selected clients **before**
invoking any CLI, and refuses to overwrite an existing Recallum setup unless you pass
`--force-mcp`.

For an installation that keeps updating from the private repository rather than this checkout:

```bash
export RECALLUM_API_KEY=...
plugins/recallum-memory/scripts/install.sh --target both --remote
```

GitHub SSH access must already work. The checkout used to launch the script can be removed after
installation.

### Declarative install (Claude Code global settings)

`install.sh --claude-scope user` writes the plugin into `~/.claude/settings.json`. To skip the
script and declare it by hand, merge these three keys into that file:

```json
{
  "extraKnownMarketplaces": {
    "recallum-local": { "source": { "source": "github", "repo": "Zozi96/recallum-mcp" } }
  },
  "enabledPlugins": { "recallum-memory@recallum-local": true },
  "pluginConfigs": {
    "recallum-memory@recallum-local": {
      "options": { "mcp_url": "https://recallum.example.com/mcp/" }
    }
  }
}
```

Two constraints, neither cosmetic:

- **The marketplace key must be `recallum-local`.** It is not free-form: the installer checks for
  the literal id `recallum-memory@recallum-local` when deciding whether the plugin is already
  present. Declared under any other name, a later `install.sh` run reads it as missing and installs
  a second copy on top.
- **`api_token` cannot live here.** It is `sensitive` in `plugin.json`, so it goes to secure storage
  via `/plugin configure recallum-memory@recallum-local`, or to `RECALLUM_API_KEY` in the
  environment that launches Claude. Only the non-sensitive `mcp_url` is declarable.

Replace the `github` source with `{ "source": "directory", "path": "/abs/path/to/recallum-mcp" }`
to track a local checkout instead of the published repository. `enabledPlugins` resolves
user < project < local, so a `false` in a project's settings overrides the global `true`.

### The trailing slash is not cosmetic

`--url` is normalized to end in `/mcp/`. Observed against the deployed server:

```
https://recallum.zozbit.com/mcp
  -> 307  Location: http://recallum.zozbit.com/mcp/     <- HTTPS downgraded to HTTP
  -> 308  Location: https://recallum.zozbit.com/mcp/
```

Starlette's `redirect_slashes` builds that `Location` from the scheme it sees, which is `http`
because the reverse proxy in front of it does not forward `X-Forwarded-Proto` (or uvicorn does not
trust it). A 307 preserves method, body **and headers**, so a client starting at the slashless URL
either resends `Authorization: Bearer <key>` over cleartext HTTP, or strips it on the scheme change
and then fails to authenticate. Requesting `/mcp/` directly avoids the redirect.

The real fix belongs on the server:

```bash
uvicorn ... --proxy-headers --forwarded-allow-ips='<reverse-proxy-ip>'
```

## How the API key is handled

The installer never reads, prints, or stores your key. Each client gets there differently:

| | Codex | Claude Code | Grok Build |
| --- | --- | --- | --- |
| MCP registration | `codex mcp add`, separate from the plugin | `.mcp.json` bundled **inside** the plugin | `grok mcp add` → `~/.grok/config.toml` (required; Grok does not resolve Claude `${user_config.*}`) |
| Endpoint | `--url` | `userConfig.mcp_url`, passed by the installer | `--url` written into config.toml |
| Key | `--token-env-var` names an env var, resolved at connect time | `${RECALLUM_API_KEY:-${user_config.api_token}}` | `Authorization: Bearer ${--token-env-var}` in config.toml |
| Key set by | you, in your shell | environment, or masked fallback via `/plugin configure` | you, in your shell |

The key is deliberately **not** passed as `--config api_token=...`: that would put the credential
into `argv`, shell history, and the process list. Only the non-sensitive endpoint is scripted.

## After installing

**Codex** — export the token, then start a new thread and trust the hook:

```bash
export RECALLUM_API_KEY=...        # put this in your shell profile
```

Open `/hooks`, confirm the Recallum hook path points at this installation, and trust it.

**Claude Code** — export the same variable before launching Claude, or store a masked fallback,
then restart the session:

```bash
export RECALLUM_API_KEY=...
```

```text
/plugin configure recallum-memory@recallum-local
```

`RECALLUM_API_KEY` takes precedence. Unset it before launching Claude to use the stored
`api_token` fallback. When the variable is set, Claude Code may still warn that one `userConfig`
option is unset during installation; the MCP connection uses the environment variable normally.

**Grok Build** — export the token, then start a new session:

```bash
export RECALLUM_API_KEY=...
grok mcp doctor recallum    # handshake OK, tools discovered
```

A config.toml entry for `recallum` shadows any plugin-bundled MCP that still shows the unresolved
`${user_config.mcp_url}` placeholder from Claude compatibility.

## Verify

```bash
codex mcp get recallum --json     # Codex
claude mcp list | grep recallum   # Claude Code -> plugin:recallum-memory:recallum ... Connected
claude plugin details recallum-memory
grok mcp doctor recallum          # Grok Build
grok plugin details recallum-memory
```

`claude plugin details` / `grok plugin details` should report the skills and hooks; Grok's healthy
MCP path is the config.toml entry, not the Claude `userConfig` placeholder.

The `recallum-setup` skill walks the full diagnostic path, including a cross-session check, without
ever revealing the key.

### Tool names differ per client

Codex registers the server under its bare name; Claude Code namespaces a plugin-bundled server as
`plugin:<plugin>:<server>` and rewrites every character outside `[A-Za-z0-9_-]` to `_` when building
tool ids:

| Client | Prefix |
| --- | --- |
| Codex | `mcp__recallum__` |
| Claude Code | `mcp__plugin_recallum-memory_recallum__` |
| Grok Build | `recallum__` (via `search_tool` / `use_tool`) |

Both skills document this, and the `SessionStart` hook emits whichever spelling matches the running
client. This is why the plugin behaves identically across clients despite the different tool ids.

## Reconfiguring

Changing the endpoint:

```bash
plugins/recallum-memory/scripts/install.sh --url https://new.example.com/mcp --force-mcp
```

On Claude Code this uninstalls and reinstalls the plugin. Export `RECALLUM_API_KEY` before launching
Claude, or re-run `/plugin configure` to restore a masked fallback.

## Uninstall

```bash
codex mcp remove recallum && codex plugin remove recallum-memory
claude plugin uninstall recallum-memory@recallum-local
grok mcp remove recallum && grok plugin uninstall recallum-memory
```

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Tools missing after install | Start a **new** session; both clients discover MCP tools only at session start |
| Tools missing in `claude -p` | A restricted `agent` in `settings.json` can pin a tool allowlist that excludes MCP tools. Check the `agent` key and its `tools:` frontmatter |
| `No such tool available: mcp__plugin_recallum-memory_recallum__*` | Not the same as missing. Claude Code leaves plugin-bundled MCP tools behind `ToolSearch` instead of listing them, so a blind call to the fully qualified name fails while the server is connected. Search for the tool, then call it. `permissions.allow` does **not** make them load eagerly |
| Stale Codex plugin behaviour after `git pull` | Rerun `plugins/recallum-memory/scripts/install.sh --target codex`, then start a new session |
| Stale Claude Code plugin behaviour after `git pull` | The installed copy is a versioned cache under `~/.claude/plugins/cache/`, not your checkout. Rerun `plugins/recallum-memory/scripts/install.sh --target claude --force-mcp`, then start a new session |
| Claude authentication failure | Export `RECALLUM_API_KEY` before launching Claude, or run `/plugin configure recallum-memory@recallum-local`; the environment variable wins when both exist |
| Grok authentication / handshake failure | Export `RECALLUM_API_KEY` and ensure `~/.grok/config.toml` has a real URL plus `Bearer ${RECALLUM_API_KEY}` — not `${user_config.mcp_url}`. Rerun `install.sh --target grok` |
| Hook never fires | Confirm the plugin is enabled and that `python3` or `python` is on the `PATH` of the process that launched the client. The hook fails open, so a missing interpreter is silent |
| Codex authentication failure | The named environment variable is missing from the environment that launched Codex |

## Development

```bash
python3 plugins/recallum-memory/tests/test_plugin.py     # hook, manifest, and installer tests
claude plugin validate . --strict                        # Claude marketplace manifest
claude plugin validate plugins/recallum-memory --strict  # Claude plugin manifest
grok plugin validate plugins/recallum-memory             # Grok plugin (plugin.json + components)
uv run ruff check plugins/recallum-memory
```

`plugins/recallum-memory/.ruff.toml` pins `target-version = "py39"` for this directory. The
repository targets Python 3.14, and at that target `ruff format` rewrites the hook into 3.14-only
syntax (PEP 758 unparenthesized `except A, B:`), which is a `SyntaxError` on the interpreters this
hook actually has to run on. A test enforces the same floor via
`ast.parse(..., feature_version=(3, 9))`.
