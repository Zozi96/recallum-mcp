# Security audit — S004

verdict: pass
bounce_to: none
attempt: 1

## Reasons

- **`hooks.json` was audited as code, because it ships an executable command line inside a distributed bundle.** Every expansion on L6 is double-quoted (`"$p"`, `"$y"`, `"$p/hooks/recallum_hook.py"`). There is no `eval`, no glob, and no unquoted substitution — so no word-splitting or injection path.
- **The fallback is safe.** `cat >/dev/null 2>&1; exit 0` drains stdin (no SIGPIPE back to the host), writes nothing to stdout, and exits 0. It leaks nothing a hook consumer would ingest.
- **Environment-variable control is not an escalation.** An attacker who can set `PLUGIN_ROOT` for the `agy` process also controls `PATH`, so `command -v python3` is already hijackable. The hook grants nothing beyond what env control already grants against any program, and the `-f` guard means a foreign `PLUGIN_ROOT` falls through to the no-op.
- **Dormancy does not change the verdict.** Shipping a dormant executable command is not materially worse than a dormant config *here*, because the command is safe as written and execs only the repo's own vetted `recallum_hook.py`. Dormancy amplifies unsafe code; it does not create it.
- **The absence pin is the whole story.** `git log main..HEAD -- plugins/recallum-memory/hooks/recallum_hook.py` is **empty** — the theme never touches the script. The `PLUGIN_ROOT` branches at L178 and L220 predate it (`70e54b72`, `d750d228`, `4a759446`). No Antigravity path was added elsewhere under a different name.

## Gaps

- None blocking.
- **Defense-in-depth** (`hooks.json` L6): the generic unnamespaced `PLUGIN_ROOT` takes precedence over the namespaced `GROK_`/`CLAUDE_` variables, inverting `recallum_hook.py` L176-180's own order. No exploit — the `-f` check gates it — but preferring namespaced variables first would remove the collision surface.
- **For whoever enables dispatch**: `_emit` (`recallum_hook.py` L520) prints Claude-shaped `hookSpecificOutput`, which `agy` would not parse — theme constraint 6 established those fields do not exist in the binary. Cosmetic while dispatch never happens; revisit the command line if it is ever turned on.
