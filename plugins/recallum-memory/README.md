# Recallum Memory plugin

Durable, project-aware memory for **Codex** and **Claude Code**, backed by a self-hosted Recallum
MCP server.

The plugin ships:

- two skills — `recallum-memory` (when and how to use memory) and `recallum-setup` (install and
  diagnose);
- two hooks — `SessionStart` injects the canonical project key, `UserPromptSubmit` nudges recall
  when a prompt mentions memory. Both fail open;
- the MCP wiring for each client.

## Prerequisites

- A reachable Recallum server. The endpoint must be HTTPS and its path must end in `/mcp` or
  `/mcp/`. Plain HTTP is accepted only for `localhost` / `127.0.0.1`. Defaults to
  `https://recallum.zozbit.com/mcp/`.
- `python3` on `PATH` — the hooks run under it. Any 3.9+ interpreter works.
- The `codex` and/or `claude` CLI.

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
| `--target TARGET` | `auto` | `auto`, `codex`, `claude`, or `both`. `auto` uses every detected CLI; `codex`/`claude`/`both` fail if a named CLI is missing |
| `--token-env-var NAME` | `RECALLUM_API_KEY` | **Codex only.** Environment variable Codex reads the bearer token from |
| `--claude-scope SCOPE` | `user` | **Claude Code only.** `user`, `project`, or `local`; applied to the marketplace and the plugin install |
| `--force-mcp` | off | Replace an existing setup: a differing Codex MCP definition, or an already-installed Claude Code plugin |
| `--dry-run` | off | Validate and print the plan without mutating anything |
| `--help` | | Usage |

The script validates the URL and both marketplace manifests **before** invoking any CLI, and
refuses to overwrite an existing Recallum setup unless you pass `--force-mcp`.

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

The installer never reads, prints, or stores your key. The two clients get there differently:

| | Codex | Claude Code |
| --- | --- | --- |
| MCP registration | `codex mcp add`, separate from the plugin | `.mcp.json` bundled **inside** the plugin |
| Endpoint | `--url` | `userConfig.mcp_url`, passed by the installer |
| Key | `--token-env-var` names an env var, resolved at connect time | `userConfig.api_token`, declared `sensitive` and stored by Claude Code |
| Key set by | you, in your shell | you, via `/plugin configure` |

The key is deliberately **not** passed as `--config api_token=...`: that would put the credential
into `argv`, shell history, and the process list. Only the non-sensitive endpoint is scripted.

## After installing

**Codex** — export the token, then start a new thread and trust the hook:

```bash
export RECALLUM_API_KEY=...        # put this in your shell profile
```

Open `/hooks`, confirm the Recallum hook path points at this installation, and trust it.

**Claude Code** — set the key, then restart the session:

```
/plugin configure recallum-memory@recallum-local
```

## Verify

```bash
codex mcp get recallum --json     # Codex
claude mcp list | grep recallum   # Claude Code -> plugin:recallum-memory:recallum ... Connected
claude plugin details recallum-memory
```

`claude plugin details` should report 2 skills, 2 hooks, and 1 MCP server.

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

Both skills document this, and the `SessionStart` hook emits whichever spelling matches the running
client. This is why the plugin behaves identically in both despite the different tool ids.

## Reconfiguring

Changing the endpoint:

```bash
plugins/recallum-memory/scripts/install.sh --url https://new.example.com/mcp --force-mcp
```

On Claude Code this uninstalls and reinstalls the plugin, so re-run `/plugin configure` afterwards
to set the key again.

## Uninstall

```bash
codex mcp remove recallum && codex plugin remove recallum-memory
claude plugin uninstall recallum-memory@recallum-local
```

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Tools missing after install | Start a **new** session; both clients discover MCP tools only at session start |
| Tools missing in `claude -p` | A restricted `agent` in `settings.json` can pin a tool allowlist that excludes MCP tools. Check the `agent` key and its `tools:` frontmatter |
| Claude Code reports `userConfig option not yet set` | `api_token` is unset — run `/plugin configure recallum-memory@recallum-local` |
| Hook never fires | Confirm the plugin is enabled and that `python3` or `python` is on the `PATH` of the process that launched the client. The hook fails open, so a missing interpreter is silent |
| Codex authentication failure | The named environment variable is missing from the environment that launched Codex |

## Development

```bash
python3 plugins/recallum-memory/tests/test_plugin.py     # hook, manifest, and installer tests
claude plugin validate . --strict                        # marketplace manifest
claude plugin validate plugins/recallum-memory --strict  # plugin manifest
uv run ruff check plugins/recallum-memory
```

`plugins/recallum-memory/.ruff.toml` pins `target-version = "py39"` for this directory. The
repository targets Python 3.14, and at that target `ruff format` rewrites the hook into 3.14-only
syntax (PEP 758 unparenthesized `except A, B:`), which is a `SyntaxError` on the interpreters this
hook actually has to run on. A test enforces the same floor via
`ast.parse(..., feature_version=(3, 9))`.
