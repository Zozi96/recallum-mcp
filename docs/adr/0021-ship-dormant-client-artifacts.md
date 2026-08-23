# ADR 0021: Ship a dormant client artifact only under four conditions

## Status
Accepted

## Context
This batch put two files in the plugin bundle that the client accepts and does not use:

- `plugins/recallum-memory/mcp_config.json` (S001) — `agy plugin validate` reports `mcpServers : 1 processed`, `agy plugin install` copies it into `~/.gemini/config/plugins/recallum-memory/`, and the server never reaches the runtime server list (OQ4).
- `plugins/recallum-memory/hooks.json` (S004) — `hooks : 1 processed`, installed, and no `SessionStart` dispatch was ever observed (OQ1).

Two separate gates ruled each file kept, and reached that verdict independently on matching reasoning. Two instances arrived at by two stories is enough to state the rule once instead of leaving it as two local calls that the next story re-litigates from scratch — but not enough to state it loosely. The hazard is specific and it is not the file: it is that `1 processed` reads as "working" to anyone who runs the command, so a dormant artifact ships its own false advertisement.

Note that dormancy is not uniform. `mcp_config.json` is dormant *for the plugin-bundle path only*; the same shape written by `install.sh` into `~/.gemini/config/mcp_config.json` is the one path that does register the server (ADR 0019). `hooks.json` has no working counterpart anywhere.

## Decision
A bundled artifact that the client parses but does not act on may ship when all four hold:

1. **The client validates it.** A file the client rejects is a broken bundle, not a dormant one.
2. **Nothing regresses.** Its presence must not change any surface that does work. `test_skills_and_mcp_servers_unaffected_by_hooks_json_presence` proves this for `hooks.json` by validating the bundle with and without the file and comparing agy's `skills` and `mcpServers` report lines; `test_legacy_mcp_files_untouched` proves the analogous point for `mcp_config.json` against the pre-existing `mcp.json` / `.mcp.json`.
3. **The misleading indicator is the client's own output, and is neutralised in docs.** We do not author the `1 processed` line; we are obliged to contradict it. Per ADR 0020 the hedge names what was actually observed.
4. **It is a forward-compatible seam in the shape the client already specifies** — not a shape invented in anticipation of one. `serverUrl` and the object-form `SessionStart` are what agy's own validator accepts today.

If a condition fails, do not ship the file.

## Alternatives considered
- Treat these as two local calls needing no general rule: rejected. Both gates reasoned from scratch and reached the same four points; the third story to face this would do it again, and the failure mode of getting it wrong (shipping a file that advertises a capability the product does not have) is a user-facing honesty problem, not a tidiness one.
- Omit both files until agy consumes them: rejected, and it is the strongest alternative. It costs nothing today and removes the false-advertisement hazard entirely. It was rejected because `mcp_config.json` is the artifact `agy plugin install` looks for by name, so its absence is indistinguishable from an unsupported plugin, and because re-deriving the accepted schema later is exactly the work S001 and S004 did against a brief that was wrong about it (theme constraint 5).
- Ship them with an in-file comment marking them inert: rejected; JSON has no comments, and a `"_comment"` key is a schema risk against a validator whose strictness on unknown keys was not tested.
- Gate them behind an env var or a build flag: rejected as machinery for a two-file, zero-branch decision.

## Consequences
The bundle contains two files whose only present function is to make `agy plugin validate` print a line. An operator who runs that command and reads no documentation will conclude the MCP server and the hook are live; only `docs/clients.md` and `SKILL.md` say otherwise, and nothing forces them to be read. This is the accepted cost of condition 3 rather than a gap in it.

Neither file has an expiry. If agy never consumes them they stay dormant indefinitely, and the reasoning above stays valid — which also means nothing prompts a re-check when agy *does* start consuming them. The re-check trigger is an agy release note, not a test.

Condition 2 is the only one the suite enforces. Conditions 1, 3, and 4 are review obligations.
