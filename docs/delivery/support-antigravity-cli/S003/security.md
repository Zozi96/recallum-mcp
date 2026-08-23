# Security audit — S003

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- No secret reaches any output path in the supported config shape. A literal token was probed across text and `--json`, healthy and every unhealthy fixture (missing header, wrong path, plain HTTP, `0644`, list-valued header, `oauth.client_secret`): `_redact_bearer` (recallum_doctor.py:91-105) emits only `Bearer *** (literal)` / `missing` / `invalid`. There is no partial redaction, so no prefix or suffix can escape. `_safe_url` (:139-166) strips query, fragment and userinfo before the URL enters `native_mcp`. No exception path prints file contents; all readers catch (`_read_json` :41-45, `_file_mode` :85-89, `_antigravity_endpoint_problem` :513-541).
- A hostile `agy` is contained. `_antigravity_plugin_present` (:544-573) reduces subprocess output to a single bool, so no attacker-controlled string is copied into the report. Probed with control characters in `components[]`, 20k-element arrays, non-JSON stdout and exit 3: no traceback, no leak, no injection. `json.loads` only, no unsafe deserialization. The PATH exec of `agy` is narrower than the pre-existing `claude`/`codex`/`grok` call sites (:337, :397, :428) because it runs only after a `recallum` entry is found, and a writable PATH directory already implies user-level code execution.
- Skips cannot mask a security finding. `_antigravity_plugin_present` is called last in `_antigravity` (:589), after auth, permission and endpoint checks have appended to the shared `problems` list; returning `None` only omits `plugin_present`.
- `stat.S_IMODE` retains setuid/setgid/sticky bits, so `2600` and `4600` fail the `!= "0600"` gate (:249). `path.stat()` follows symlinks, reporting the target's real mode.

## Gaps — security

- Low, defense-in-depth, pre-existing in `_safe_url` but newly reachable for `serverUrl`: a token in the URL **path** is echoed verbatim (`serverUrl=https://api.recallum.ai/<TOKEN>/mcp/` printed it in both modes, :163). Not a shape the installer or server produces, and :539 already flags it as a problem.
- Low: `_record_permission` fires only when `auth == "Bearer *** (literal)"` (:249), so a literal token under a differently-cased header (`AUTHORIZATION`) or in the `serverUrl` query leaves a `0644` file unflagged. Both still exit 1 via `auth: … bearer is missing`. Open: whether `agy` canonicalizes header keys.

## Correctness defects found during this audit — NOT security, but material

These do not block the security verdict. They are recorded here because they defeat the story's stated purpose and are routed back to stage 4 by the leader.

- **D1** A config with `Bearer ${RECALLUM_API_KEY}` at mode `0644` reports **healthy, exit 0**. Theme constraint 3 establishes that Antigravity performs no env-var expansion, so that config can never work — yet the doctor calls it fine.
- **D2** `agy plugin list --json` prints `No imported plugins.`, not JSON, when no plugins are installed. Leader-verified against the real binary: `HOME=$(mktemp -d) agy plugin list --json` → `No imported plugins.`, exit 0. `_run_json` therefore returns `None` and the plugin check **silently skips exactly when the plugin is genuinely missing** — the case the check exists to catch. Tests passed because the fake `agy` always emits JSON; the fixture does not match reality.
