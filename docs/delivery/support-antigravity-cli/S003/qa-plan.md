# QA plan — S003: Diagnose Antigravity CLI registration in `recallum_doctor.py`

## Risks and cheapest detection layer

1. **High — absent-client path leaks a key or raises.** No `~/.gemini` dir must silently omit `"Antigravity CLI"` from `report["clients"]`, matching `_claude`/`_codex`/`_grok`/`_cursor`. Unit: call `_antigravity(home, ...)` directly on a `home` with no `.gemini` and assert it returns a falsy/empty result so `main()`'s `if value:` guard drops it. Cheapest layer — no subprocess needed.
2. **High — `serverUrl` validation regresses `_safe_url`'s existing scheme/host rule.** `http://example.com/mcp/` (non-loopback plain HTTP) and a wrong-path `serverUrl` must both land in `problems[]`. Unit: feed `_antigravity` a payload dict directly, assert the specific problem string and that `result["mcp"]["url"]` is present (not silently dropped by `_safe_url`'s invalid-URL branch, which is a distinct failure mode from "wrong path but well-formed").
3. **High — file-mode check silently no-ops.** `_record_permission` only flags mode when `auth == "Bearer *** (literal)"`; a fixture with an env-reference bearer (`Bearer ${TOKEN}`) at mode `0644` would NOT trigger a permission problem under the existing helper's logic — this is a real behavioral boundary, not a bug, and must be asserted both ways (literal bearer + bad mode = flagged; env-ref bearer + bad mode = not flagged) so a future refactor can't accidentally invert it. Unit level, `_record_permission` is already unit-tested for other clients — extend the same table.
4. **High — token redaction regresses under `--json` and text output**, for both healthy and unhealthy fixtures, plus the adversarial-token pattern from `test_doctor_adversarial_credentials_and_null_servers_are_safe` (token embedded in URL query and in `Authorization` header). Integration: subprocess `recallum_doctor.py --json` and text mode, `assertNotIn(token, output)` and `assertNotIn(token[4:], output)` (catches partial redaction that only strips a prefix).
5. **Medium — `agy plugin list` stubbing regresses `_run_json`'s subprocess contract.** Wrong argv, non-zero exit, malformed JSON, or `agy` absent from `PATH` must never raise — `_run_json` already returns `None`/`{}` on failure for other clients, this only needs a `plugin_present: true` / absent-and-no-exception check specific to Antigravity's `mcpServers` shape. Integration (subprocess with fake `agy` on `PATH`), because `_run_json`'s subprocess-error handling is only real when exercised via `subprocess.run`, not by calling `_antigravity` with a monkeypatched function.
6. **Medium — regression in sibling clients from the new client-tuple entry.** Adding `("Antigravity CLI", _antigravity(...))` to the L561-564 tuple must not change `Claude Code`/`Codex`/`Grok Build`/`Cursor` output or ordering. Integration: run the full existing `test_doctor_healthy_configuration_exits_zero` and adversarial-credentials suite unmodified after the change lands; a diff in those unrelated assertions is the regression signal, not a new test.
7. **Low — exit-code aggregation.** Antigravity problems must add to the same shared `problems` list and produce exit `1`, exactly like every other client. Integration: one healthy-except-Antigravity fixture, assert `returncode == 1` and the specific Antigravity problem string is present alongside an otherwise-empty client set.

## Fixture matrix (named)

All fixtures are per-test-function `tempfile.TemporaryDirectory()` homes, following `_healthy_home`/`_write`/`_write_cli` helpers already in `test_plugin.py`. New fixture writer: `_write_antigravity_config(home, *, url=..., auth=..., mode=0o600)` writing `~/.gemini/config/mcp_config.json` with a `mcpServers.recallum` (or theme.md's confirmed key name) entry, then `os.chmod`-ing it explicitly (see umask note below).

| Fixture name | Setup | Expected doctor behavior |
|---|---|---|
| `antigravity_absent` | no `~/.gemini` dir at all | no `"Antigravity CLI"` key in `clients`; exit unaffected by this client |
| `antigravity_healthy` | config present, `serverUrl` ends in `/mcp/`, literal `Authorization` header, mode `0600` | no Antigravity problem; exit `0` if nothing else fails |
| `antigravity_world_readable` | same as healthy but mode `0644` | permission problem naming the file path; exit `1` |
| `antigravity_group_readable` | mode `0640` | permission problem (mode != `0600`, same rule as world-readable — proves the check is an equality test against `0600`, not merely "not world-readable") |
| `antigravity_auth_missing` | config present, no `Authorization` header (or `headers` key absent) | auth problem naming `Antigravity CLI`; exit `1` |
| `antigravity_bad_scheme` | `serverUrl = "http://example.com/mcp/"` | URL/scheme problem; exit `1` (mirrors non-loopback-HTTP rejection already proven for other clients) |
| `antigravity_https_localhost_exception` | `serverUrl = "http://127.0.0.1:PORT/mcp/"` | no scheme problem — proves the loopback-HTTP exception applies identically to Antigravity, not just to whichever client `_safe_url` was originally written for |
| `antigravity_wrong_path` | `serverUrl` valid scheme/host but path `/mcp` (no trailing slash) or `/other/` | path problem; exit `1` |
| `antigravity_plugin_listed` | fake `agy` on `PATH` (see below) returns plugin listed + `mcpServers` present | `result["plugin_present"] is True` (or theme-agreed key), no plugin problem |
| `antigravity_plugin_not_listed` | fake `agy` present, JSON omits the recallum plugin or returns empty list | plugin-not-listed problem, since `agy` is on `PATH` |
| `antigravity_agy_absent_from_path` | no `agy` fixture, plain fake-CLI dir without it (or `PATH` scrubbed to exclude it) | plugin check silently skipped, no exception, no plugin-related problem |
| `antigravity_agy_malformed_json` | fake `agy` prints non-JSON or exits non-zero | no exception; treated the same as `agy` absent for the plugin sub-check (consistent with `_run_json`'s existing None-on-failure contract) |
| `antigravity_token_redaction` | healthy + adversarial fixtures, token embedded in `serverUrl` query and in header | `assertNotIn(token, ...)`, `assertNotIn(token[4:], ...)`, in both `--json` and text output |

## Fake `agy` stub (no real binary required)

Reuse `_write_cli(home, name, script_body)` exactly as done for `codex`/`grok`/`cursor-agent` (`test_plugin.py` L1191-1220): write an executable Python script named `agy` into a directory prepended to `PATH` via the `env` dict returned by `_fake_clis`, dispatching on `sys.argv[1:] == ['plugin', 'list', '--json']` and printing a canned JSON payload (matching the `mcpServers`-present/absent, plugin-listed/not-listed cases). This is the identical pattern the story text and theme.md's constraint on stubbing already prescribe — no dependency on Antigravity being installed, and it exercises the real `subprocess.run` + JSON decode path rather than mocking `_run_json` itself, which would under-test the failure modes in risk 5.

CI-vs-local divergence: locally `/home/zozi/.local/bin/agy` is real and may leak onto `PATH` if a test forgets to construct an isolated `PATH`. Every Antigravity doctor test MUST pass an explicit `env["PATH"]` built only from the fake-CLI directory plus the minimum needed for Python itself (mirror `_fake_clis`'s existing pattern precisely) — never inherit `os.environ["PATH"]`. This is the one place local runs and CI can silently diverge (CI has no real `agy`, so a test that "passes" locally only because it hit the real binary would fail in CI, or worse, pass for the wrong reason). Add one explicit assertion of intent: `antigravity_plugin_listed`/`_not_listed` must assert against a distinguishing field only the fake binary would emit (e.g., a sentinel version string), so a silent fallthrough to a real local `agy` is caught by the assertion, not just by the PATH hygiene.

## Umask / file-mode strategy

File-mode assertions are inherently sensitive to the process umask, since `Path.chmod`/`open(..., mode=...)` and any code path that creates a file rather than explicitly chmod-ing it will have the requested mode ANDed against the running umask. Two-part defense:

1. **Never rely on file-creation mode.** Every fixture writer creates the file via ordinary `Path.write_text`, then calls `path.chmod(0o600)` (or `0o644`/`0o640`) **explicitly, in a separate step**, exactly as the existing `key_file.chmod(0o600)` / `creds.chmod(0o600)` precedent at L1898/L2012 does. `chmod` sets the mode directly and is not subject to umask — this sidesteps the whole class of umask interference for fixture setup.
2. **Assert the doctor's own read of the mode, not the filesystem's raw mode**, i.e. assert on `report["clients"]["Antigravity CLI"]["file_mode"]` (mirroring how `_record_permission` populates `result["file_mode"]` for other clients) or on the `problems[]` string, not by re-`stat`-ing the file in the test process — this proves `_file_mode()` (which itself uses `stat.S_IMODE`, immune to umask by definition since it reads back an already-set mode) is wired correctly end to end, and removes any temptation to derive expected mode from `0o666 & ~umask` arithmetic in the test itself.
3. As an explicit belt-and-braces check, one test (`antigravity_world_readable`) should set the test process umask to a restrictive value (e.g. `os.umask(0o077)`) around the fixture-creation step and confirm the permission problem still fires — this is the concrete proof that a restrictive local umask cannot mask the mode-`0644` bug by accidentally producing a `0600` file. Save and restore the umask in a `try/finally` (umask is process-global and leaks across tests otherwise).

## Sentinel-token technique

Every fixture uses a fabricated, clearly-fake token value, following the existing pattern (`token = "rcl_adversarial_secret_789"` in `test_doctor_adversarial_credentials_and_null_servers_are_safe`) — never a real or realistic-looking credential, never read from environment or a real Recallum deployment. Assertions are `assertNotIn(token, output)` and `assertNotIn(token[4:], output)` (the second catches redaction that only strips a fixed-length prefix rather than the whole secret) applied to both `--json` and text-mode stdout+stderr. No test ever prints, logs, or persists the sentinel outside the fixture's own temp directory, and the temp directory is torn down by `tempfile.TemporaryDirectory()`'s own context-manager cleanup — no manual credential-file deletion step to forget.

## Operational done criteria (stage 8)

Stage 8 returns `pass` only when, in CI (no real `agy`, no real `~/.gemini`) and using an isolated `PATH`/`HOME` per test:
- All fixtures in the matrix above run as new `unittest` methods in `test_plugin.py` (or a new `TestAntigravityDoctor` class) and pass.
- `antigravity_absent`: `"Antigravity CLI" not in report["clients"]` and doctor exit code is unaffected by Antigravity specifically (equals whatever the other-clients-only baseline produces).
- `antigravity_healthy`: no string containing `"Antigravity"` appears in `report["problems"]`; exit `0` when combined with an otherwise-healthy fixture.
- `antigravity_world_readable` and `antigravity_group_readable`: `problems[]` contains an entry naming both "permission" and the literal config file path; exit `1`.
- `antigravity_auth_missing`: `problems[]` contains an entry naming `"Antigravity CLI"` and `"auth"`; exit `1`.
- `antigravity_bad_scheme` and `antigravity_wrong_path`: `problems[]` contains a URL/path-shaped entry; exit `1`.
- `antigravity_https_localhost_exception`: no such entry.
- `antigravity_plugin_listed`/`_not_listed`/`_agy_absent_from_path`/`_agy_malformed_json`: no `Traceback` in stdout+stderr in any of the four; `plugin_present` (or the agreed key) is `True` only in the listed case; PATH-isolation sentinel assertion passes.
- `antigravity_token_redaction`: sentinel token and its trailing substring are absent from all four output combinations (text/json × healthy/unhealthy).
- The full pre-existing `test_plugin.py` suite (all clients) still passes unmodified — proves no cross-client regression from the tuple edit.
- `mypy`/whatever static check gates this file today still passes on `recallum_doctor.py` (new function must be fully typed, matching `_claude`/`_codex` signatures).

Any test that is skipped, xfailed, or passes only because it silently fell through to a real `agy`/`~/.gemini` on the host is a fail, not a pass.

## Blocking dependencies

- theme.md's verified constraints for the exact `~/.gemini/config/mcp_config.json` key names (`serverUrl` vs `url`, `mcpServers` key name) and `agy plugin list --json` output shape — this story is stated as buildable against those without S001/S002 landing, but a mismatch between the fixture's assumed shape and the real S001/S002 output would only surface as a later cross-check, not in this suite. Flag any such drift back to spec-review rather than silently adjusting fixtures to match a differently-shaped implementation.
- No real network, no real Recallum server, no real Antigravity install needed anywhere in this suite — everything is fixture- and fake-CLI-driven by design, matching the existing doctor test precedent.
- CI must not have a real `agy` on `PATH` reachable through an un-isolated `PATH` env — if CI's runner image ever installs `agy` globally, the PATH-isolation discipline above becomes load-bearing rather than defensive.

## Deliberate coverage gaps

- **No test of `agy`'s real binary output shape.** This plan only proves the doctor correctly parses whatever JSON a stub emits; whether the real `agy plugin list --json` matches theme.md's assumed shape is a manual/S001-S002-integration cross-check, explicitly deferred by the story's own "Dependencies" section, not this suite's job.
- **No test of config *repair* or *write* behavior.** The doctor is read-only diagnostics per the story's "Out of scope"; no fixture attempts to fix a broken config.
- **No hook-path diagnostics** (`recallum_hook.py` client detection for Antigravity) — owned by S004, gated on open questions OQ1-OQ3 not yet resolved.
- **No docs/string assertions** (README rows, `docs/clients.md`) — owned by S005.
- **No performance/timing test on the `agy` subprocess call** — `_run_json` has no timeout differentiation from other clients; if this becomes a real risk (slow/hanging `agy`), it belongs to a future story once actual `agy` latency is observed, not speculatively here.
- **No test of concurrent doctor invocations** — `recallum_doctor.py` is a single-shot read-only CLI process with no shared mutable state across invocations; ordering/concurrency concerns from the general QA checklist do not apply to this story.
