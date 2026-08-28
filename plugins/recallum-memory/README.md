<p align="center">
  <img src="assets/logo.svg" alt="Recallum" width="132" height="132" />
</p>

# Recallum Memory plugin

Durable, project-aware memory for **Cursor**, **Grok Build**, **Codex**, **Claude Code**,
**Devin CLI**, and **Antigravity CLI**, backed by a self-hosted Recallum MCP server.

The plugin ships:

- two skills — `recallum-memory` (load context and capture verified reusable knowledge) and
  `recallum-setup` (install and diagnose);
- shared hooks — Codex, Claude Code, and Grok wire `SessionStart` plus `UserPromptSubmit`; Cursor
  wires `sessionStart` and adds an always-applied rule as a delivery fallback; Devin may wire
  SessionStart through `.devin/hooks.v1.json` if it supports plugins, but hook dispatch is
  unconfirmed (see docs/clients.md). Antigravity CLI ships the same `hooks.json`, accepted by
  `agy plugin validate` (`hooks : 1 processed`), but dispatch is unconfirmed — `agy` gates every
  session behind Google OAuth sign-in before any hook is reachable (see docs/clients.md). All fail
  open;
- the MCP wiring for each client.

One plugin package, six native entry points — not a Claude-only addon:

| Client | Marketplace index | Plugin metadata |
| --- | --- | --- |
| Cursor | `.cursor-plugin/marketplace.json` | `.cursor-plugin/plugin.json` |
| Grok Build | `.grok-plugin/marketplace.json` | `plugin.json` |
| Codex | `.agents/plugins/marketplace.json` | `.codex-plugin/plugin.json` |
| Claude Code | `.claude-plugin/marketplace.json` | `.claude-plugin/plugin.json` |
| Devin CLI | n/a — closed beta; use `devin mcp add` or write `~/.config/devin/mcp_config.json` | n/a — `.devin/hooks.v1.json` if plugin hooks are supported |
| Antigravity CLI | n/a — `agy plugin install <dir>` (local dir or HTTPS GitHub URL) | `plugin.json` |

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

## Cursor

Preferred path — let the installer register the marketplace and write a desktop-safe MCP entry:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target cursor --url https://recallum.example.com/mcp/
# Or with auto (includes Cursor when cursor-agent/agent is on PATH):
plugins/recallum-memory/scripts/install.sh --url https://recallum.example.com/mcp/
```

That:

1. Adds marketplace `recallum-local` via `cursor-agent` / `agent` (git URL; use `--force-mcp` to reindex).
2. Writes `~/.cursor/mcp.json` server `recallum` with the real URL and a **mode-600 literal Bearer**
   (Cursor desktop does not expand shell `${ENV}`, and plugin Configure is often unavailable for
   user marketplaces).
3. If a plugin cache already exists, patches its `mcp.json` the same way and moves Claude’s
   `.mcp.json` aside so Cursor does not load unresolved `${user_config.*}` URLs.

Then install the plugin **in the Cursor UI** (the CLI cannot install plugins): Settings → Plugins →
`recallum-local` → `recallum-memory`, or `/plugins` in `cursor-agent`. Fully quit and reopen Cursor.

For one-off local CLI testing without marketplace install:

```bash
agent --plugin-dir /path/to/recallum-mcp/plugins/recallum-memory
```

Cursor loads the plugin MCP server from `mcp.json` only when the Cursor manifest references it as
`"mcp": "./mcp.json"`. The Cursor server key is `recallum_memory`, not `recallum`: Claude Code ships
a root `.mcp.json` under the name `recallum` with `${user_config.*}` placeholders, and Cursor merges
plugin MCP configs by server name. If both use `recallum`, the Claude entry overwrites the env-var
Cursor entry and zero Recallum tools load. Claude's server name and tool prefix are unchanged.
Cursor's `sessionStart` hook emits top-level `additional_context`, but delivery is best-effort and
it cannot run before every prompt. The always-applied rule carries the exact canonical-project-key
fallback. Recallum tools appear in Cursor's Available Tools list without a stable textual prefix.

## Devin

Devin support is provided through the user-scope MCP config
`~/.config/devin/mcp_config.json`:

```bash
export RECALLUM_API_KEY=rcl_YOUR_API_KEY
plugins/recallum-memory/scripts/install.sh --target devin --url https://recallum.example.com/mcp/
```

The installer writes the `recallum` server with a literal Bearer token (mode 600)
and preserves any pre-existing `mcpServers` entries. Devin plugins are closed beta, so
`install.sh` does **not** run `devin plugins install`; if your Devin build supports
plugins, install the recallum-memory skill manually and optionally wire
`.devin/hooks.v1.json` for `SessionStart`. Hook dispatch through the plugin is expected
but unconfirmed. Tools appear as `mcp__recallum__*`.

## Prerequisites

- A reachable Recallum server, yours. The endpoint must be HTTPS; plain HTTP is accepted only for
  `localhost` / `127.0.0.1`. Cursor requires the exact `/mcp/` path to avoid an authenticated
  redirect. `scripts/install.sh` accepts `/mcp` or `/mcp/` for the other clients and normalizes it
  to `/mcp/`. It defaults to `https://recallum.zozbit.com/mcp/`; the Cursor marketplace has no
  endpoint default, so nobody inherits another operator's server without choosing it.
- `python3` on `PATH` — the hooks run under it. Any 3.9+ interpreter works.
- The `agent`, `codex`, `claude`, `grok`, `devin`, and/or `agy` CLI as applicable.

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

### Doctor

Run the read-only, stdlib-only doctor to inspect client registrations, files, environment status,
permissions, auth shape, and installed-version drift without printing secrets:

```bash
python3 plugins/recallum-memory/scripts/recallum_doctor.py
python3 plugins/recallum-memory/scripts/recallum_doctor.py --json
```

### Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--url URL` | `https://recallum.zozbit.com/mcp/` | Recallum MCP endpoint |
| `--target TARGET` | `auto` | `auto`, `codex`, `claude`, `grok`, `cursor`, `devin`, `antigravity`, or `both`. `auto` uses every detected CLI (including `cursor-agent`/`agent` and `devin`); `both` is Codex + Claude Code only; explicit targets fail if that CLI is missing |
| `--token-env-var NAME` | `RECALLUM_API_KEY` | Environment variable Codex and Grok read the bearer token from at connect time. For Claude Code it is only an installer-time *source*: the value is copied into userConfig storage, because `.mcp.json` reads `${user_config.api_token}` and never the environment |
| `--claude-scope SCOPE` | `user` | **Claude Code only.** `user`, `project`, or `local`; applied to the marketplace and the plugin install |
| `--remote` | off | Register the private GitHub repository instead of this local checkout |
| `--force-mcp` | off | Replace an existing setup: a differing Codex/Grok MCP definition, or an already-installed Claude Code plugin |
| `--api-key-file PATH` | off | Read the API key from a file (preferred for non-interactive installs). Never pass the key on the command line |
| `--no-store-api-key` | off | Skip prompting/persisting the key; only register marketplaces/MCP |
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
- **`api_token` cannot live here as a hand-written secret.** It is `sensitive` in `plugin.json`.
  The installer stores it in `~/.claude/.credentials.json` under `pluginSecrets` (same place as
  `/plugin configure recallum-memory@recallum-local`). Exporting `RECALLUM_API_KEY` is **not**
  enough on its own — `.mcp.json` resolves `${user_config.api_token}`, so the value has to reach
  userConfig storage via the installer or `/plugin configure`. Only the non-sensitive `mcp_url`
  is declared in settings.

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
because the reverse proxy in front of it does not forward `X-Forwarded-Proto` (or Granian is not
configured to trust it). A 307 preserves method, body **and headers**, so a client starting at the
slashless URL either resends `Authorization: Bearer <key>` over cleartext HTTP, or strips it on the
scheme change and then fails to authenticate. Requesting `/mcp/` directly avoids the redirect.

Granian has no forwarded-header CLI switch. The server-side fix is to wrap the ASGI app and trust
only the reverse proxy's address:

```python
from granian.utils.proxies import wrap_asgi_with_proxy_headers

app = wrap_asgi_with_proxy_headers(app, trusted_hosts="<reverse-proxy-ip>")
```

## How the API key is handled

By default the installer **persists** the key so GUI and terminal clients can authenticate after
install. It never prints the value and never passes it as `claude --config api_token=...` (that
would put it in `argv`, shell history, and the process list).

**Sources** (first match wins):

1. `--api-key-file PATH` — single-line file (use mode `600`)
2. `RECALLUM_API_KEY` or `--token-env-var` already exported in the shell running the script
3. Interactive hidden prompt when stdin is a TTY

**Persistence:**

| Target | Where the key lands |
| --- | --- |
| Claude Code | `~/.claude/.credentials.json` → `pluginSecrets["recallum-memory@recallum-local"].api_token` (same store as `/plugin configure`; works for GUI) |
| All selected clients | `~/.config/recallum/env` (`export …`) and, on Linux, `~/.config/environment.d/99-recallum.conf` (desktop session after re-login) |

| | Codex | Claude Code | Grok Build |
| --- | --- | --- | --- |
| MCP registration | `codex mcp add`, separate from the plugin | `.mcp.json` bundled **inside** the plugin | `grok mcp add` → `~/.grok/config.toml` (required; Grok does not resolve Claude `${user_config.*}`) |
| Endpoint | `--url` | `userConfig.mcp_url`, passed by the installer | `--url` written into config.toml |
| Key at connect time | `--token-env-var` env var | `${user_config.api_token}` (userConfig storage only — never the environment) | `Authorization: Bearer ${--token-env-var}` in config.toml |
| Key set by installer | env file + environment.d | pluginSecrets + env file | env file + environment.d |

Pass `--no-store-api-key` to only register marketplaces/MCP and manage the secret yourself.

## After installing

**Codex** — start a new thread and trust the hook. If you used the installer default, source the
env file (or re-login for desktop):

```bash
[ -f ~/.config/recallum/env ] && . ~/.config/recallum/env
```

Open `/hooks`, confirm the Recallum hook path points at this installation, and trust it.

**Claude Code** — restart the session. With the default installer flow, the key is already in
`pluginSecrets`, so **GUI and terminal both authenticate** without a separate
`/plugin configure`. This is the whole point of the userConfig-only header: a desktop launch that
never sources your shell profile authenticates exactly like the CLI.

If you installed with `--no-store-api-key`:

```bash
export RECALLUM_API_KEY=...
# or, inside Claude:
# /plugin configure recallum-memory@recallum-local
```

**Grok Build** — source the env file (or re-login), then start a new session:

```bash
[ -f ~/.config/recallum/env ] && . ~/.config/recallum/env
grok mcp doctor recallum    # handshake OK, tools discovered
```

A config.toml entry for `recallum` shadows any plugin-bundled MCP that still shows the unresolved
`${user_config.mcp_url}` placeholder from Claude compatibility.

**Cursor** — restart or reload the window after enabling the plugin and setting both variables.
Confirm `recallum` is enabled under Settings > Tools & MCP and that its tools appear under
Available Tools.

## Verify

```bash
codex mcp get recallum --json     # Codex
claude mcp list | grep recallum   # Claude Code -> plugin:recallum-memory:recallum ... Connected
claude plugin details recallum-memory
grok mcp doctor recallum          # Grok Build
grok plugin details recallum-memory
agent mcp list                    # Cursor -> recallum enabled
agent mcp list-tools recallum     # Cursor -> Recallum tools discovered
```

`claude plugin details` / `grok plugin details` should report the skills and hooks; Grok's healthy
MCP path is the config.toml entry, not the Claude `userConfig` placeholder.

The `recallum-setup` skill walks the full diagnostic path, including a cross-session check, without
ever revealing the key.

## Optional agent-adherence benchmark

`scripts/agent_workflow_benchmark.py` is an opt-in, local-probe runner. It creates a temporary
workspace and loopback-only MCP probe, then executes only the argv supplied after `--`; it never
changes persistent client configuration or starts a commercial client by itself. The runner makes
no external requests, although a supplied commercial agent normally will. The probe uses an
ephemeral `RECALLUM_BENCHMARK_TOKEN` and exposes these temporary variables to the command:

| Variable | Meaning |
| --- | --- |
| `RECALLUM_BENCHMARK_URL` | loopback probe URL |
| `RECALLUM_BENCHMARK_TOKEN` | per-run bearer token |
| `RECALLUM_BENCHMARK_WORKSPACE` | temporary fixture workspace |
| `RECALLUM_BENCHMARK_PROMPT` | synthetic task prompt |
| `RECALLUM_BENCHMARK_PROJECT` | canonical project key |
| `GROK_HOME` (grok-build only) | disposable Grok home: real plugin state plus probe `config.toml` |

The child receives only a minimal process environment plus benchmark variables. Pass a client
credential explicitly with one or more `--pass-env NAME` flags; arbitrary parent secrets are not
inherited.

For example, using the bundled fake agent (no network):

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot \
  --client codex --policy checkpoints --repeat 3 -- \
  python3 "$PWD/scripts/fake_workflow_agent.py"
```

The runner replaces only exact placeholder arguments; it performs no shell interpolation. It
creates temporary prompt, MCP, Grok, and plugin configuration files inside the disposable
workspace. These are concrete isolated invocation patterns for currently supported client CLIs:

```bash
python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client codex \
  --policy checkpoints -- codex exec --ephemeral --skip-git-repo-check \
  --sandbox workspace-write -c '{codex_mcp_url_config}' \
  -c '{codex_mcp_token_config}' '{prompt}'

python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client claude-code \
  --policy checkpoints -- claude --setting-sources project --plugin-dir '{plugin_dir}' \
  --no-session-persistence --permission-mode acceptEdits -p '{prompt}'

python3 scripts/agent_workflow_benchmark.py --scenario session-rotation-pivot --client grok-build \
  --policy checkpoints -- grok --no-memory --no-subagents \
  --permission-mode acceptEdits --prompt-file '{prompt_file}'
```

The Codex and Grok examples expect the Recallum plugin to be installed so its session hook is
active. Claude receives a temporary copy through `--plugin-dir`; its bundled MCP endpoint is
rewritten only in that copy. The Grok example runs against a disposable `GROK_HOME` seeded from
your real Grok home (`$GROK_HOME`, else `~/.grok`) with the probe stanza overlaid onto its
`config.toml`; the child environment sets `GROK_HOME` to that directory, so the installed plugin's
hooks stay active while the Recallum MCP server points at the loopback probe. If a client reads its
model credential from an environment variable, add `--pass-env NAME` before `--`. Never pass
`RECALLUM_API_KEY`: the probe uses only its ephemeral benchmark token. The `--policy` value is a
result label, so use distinct labels for the policy or plugin variants you intentionally compare.

Repeat each scenario three times for a useful adherence sample. Fixture traces test evaluator
math; observed traces test a supplied process against the probe. Neither is a ranking or production
telemetry measurement, and prompts, queries, credentials, and memory content are never persisted.

Operational guidance lives in the versioned benchmark runbook and matrix under
`docs/delivery/openspec-memory-quality-batch/S004/runbook.md` and
`docs/delivery/openspec-memory-quality-batch/S004/benchmark_matrix.json`: per-client launch
commands, `omitted` vs `incomplete` interpretation, and what may be versioned. A report rendered
with `scripts/eval_agent_workflow.py --matrix ...` marks unconfigured or all-incomplete client
cells as gaps and never fills them from fixture traces.

### Tool names differ per client

Codex registers the server under its bare name; Claude Code namespaces a plugin-bundled server as
`plugin:<plugin>:<server>` and rewrites every character outside `[A-Za-z0-9_-]` to `_` when building
tool ids. The installer also dual-writes a native user MCP `recallum` into `~/.claude.json` for
Claude Desktop ToolSearch (`mcp__recallum__*`):

| Client | Prefix |
| --- | --- |
| Codex | `mcp__recallum__` |
| Claude Code (plugin) | `mcp__plugin_recallum-memory_recallum__` |
| Claude Code (native / Desktop) | `mcp__recallum__` |
| Grok Build | `recallum__` (via `search_tool` / `use_tool`) |
| Cursor | Recallum MCP tools in Available Tools (no stable textual prefix) |
| Devin CLI | `mcp__recallum__` |
| Antigravity CLI | **not yet determined** — no prefix constant exists; prefer skill-driven tool discovery |

Both skills document this, and the session hook emits the client-appropriate name or discovery
hint. This is why the plugin behaves consistently despite the different tool ids.

## Reconfiguring

Changing the endpoint:

```bash
plugins/recallum-memory/scripts/install.sh --url https://new.example.com/mcp --force-mcp
```

On Claude Code this uninstalls and reinstalls the plugin. Export `RECALLUM_API_KEY` before launching
Claude, or re-run `/plugin configure` to restore a masked fallback.

For Cursor, update both variables from the plugin's Settings page and reload the window.

## Uninstall

```bash
codex mcp remove recallum && codex plugin remove recallum-memory
claude plugin uninstall recallum-memory@recallum-local
grok mcp remove recallum && grok plugin uninstall recallum-memory
```

Remove the Cursor plugin from Settings; remove the marketplace separately only if no other plugin
from this repository is needed.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Tools missing after install | Start a **new** session; clients discover MCP tools when a session starts |
| Cursor tools work but no Recallum context was injected | `sessionStart` context delivery is best-effort. The always-applied rule derives the same project key and calls `context`; confirm the rule is enabled |
| Tools missing in `claude -p` | A restricted `agent` in `settings.json` can pin a tool allowlist that excludes MCP tools. Check the `agent` key and its `tools:` frontmatter |
| `No such tool available: mcp__plugin_recallum-memory_recallum__*` | Not the same as missing. Claude Code often leaves MCP tools behind `ToolSearch`. Search (`+recallum` or `select:`) then call. On **Desktop**, also confirm native `~/.claude.json` → `mcpServers.recallum` (`mcp__recallum__*`). Nested `claude mcp list` is not Desktop proof. |
| Desktop ToolSearch 0 results for `recallum` (CLI works) | Plugin hooks can run while plugin MCP never enters Desktop’s deferred catalog. Rerun `install.sh --target claude --force-mcp`, fully quit Claude.app, new session, ToolSearch `+recallum` |
| Stale Codex plugin behaviour after `git pull` | Rerun `plugins/recallum-memory/scripts/install.sh --target codex`, then start a new session |
| Stale Claude Code plugin behaviour after `git pull` | The installed copy is a versioned cache under `~/.claude/plugins/cache/`, not your checkout. Rerun `plugins/recallum-memory/scripts/install.sh --target claude --force-mcp`, then start a new session |
| Claude authentication failure | Re-run `install.sh` (pluginSecrets + native `~/.claude.json` Bearer) or `/plugin configure recallum-memory@recallum-local`. Plugin path reads `${user_config.api_token}` only; native path uses the dual-written Bearer. |
| Grok authentication / handshake failure | Export `RECALLUM_API_KEY` and ensure `~/.grok/config.toml` has a real URL plus `Bearer ${RECALLUM_API_KEY}` — not `${user_config.mcp_url}`. Rerun `install.sh --target grok` |
| Hook never fires | Confirm the plugin is enabled and that `python3` or `python` is on the `PATH` of the process that launched the client. The hook fails open, so a missing interpreter is silent |
| Codex authentication failure | The named environment variable is missing from the environment that launched Codex |

## Development

### Mid-task retrieval checkpoint evaluation

Checkpoints are semantic `recall` calls made when the active retrieval key
(`project + active objective + subsystem/hypothesis/decision`) changes materially. They are
different from the initial `context` digest and from ranking quality: the flow evaluation checks
whether an agent retrieved a critical memory before a decision, applied its observable criteria,
avoided unnecessary calls and repeated exposures (including duplicate-exposure rate and duplicated
served-character cost), and how many characters it received. It does
not replace MRR or recall@k from `recallum-admin eval`, which measure whether a known query ranks
the expected memories.

Run the deterministic, provider-independent fixture comparison from the repository root:

```bash
python3 scripts/eval_agent_workflow.py
```

Use `--scenarios PATH --runs PATH` to evaluate another pair. Scenario files are versioned JSON
with identified `corpus_keys`, initial context, ordered phases, an optional pivot, critical
memory keys, and observable application criteria. Run files must use the same scenarios for each
policy and contain only `scenario`, `policy`, `phase`, `tool`, returned memory keys, served
character counts, and applied criterion keys. Prompts, full memory content, reasoning,
credentials, and unknown fields are rejected so versioned traces remain privacy-safe. To extend
the evaluation, add a synthetic scenario and one run for every policy, then run the command and
review critical-retrieval misses alongside calls, duplicate exposures, and served characters; a
higher call count is not success by itself.

The checked-in fixtures currently report baseline `critical=0.67`, `applied=0.67`,
`unnecessary=2`, `repeated=1`, `dup-rate=0.33`, `dup-chars=100`, `recalls=3`, `chars=440`,
versus checkpoints `critical=1.00`, `applied=1.00`, `unnecessary=0`, `repeated=0`,
`dup-rate=0.00`, `dup-chars=0`, `recalls=2`, `chars=420`.

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
