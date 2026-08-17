# Security audit — S004

**Stage:** 7 security-auditor  
**Verdict:** pass  
**Bounce to:** none

## Reasons
- Versioned artifacts are identifier-only; `validate_runs` rejects prompt/content/reasoning/credentials.
- Probe token is ephemeral and loopback-only.
- Matrix scoring ignores fixture traces.
- Grok overlay replaces `config.toml` on a disposable copy and never writes the real home.

## Findings
None confirmed.

## Defense in depth (not fail)
- `--pass-env` has no denylist.
- Child still inherits real `HOME`.
- `copytree` of `~/.grok` may copy non-config secrets into the workspace `.grok/`.

## Gaps
No live grok-build run (S005).
