# ADR 0015: Keep prompt, skill, and hook guidance as separate surfaces

## Status
Accepted

## Context
S002 requires the same merge-vs-update and stale-resolution criteria in MCP prompts, `SKILL.md`, and the SessionStart hook. S001/S005 also name tools in README, clients.md, skill, and hook. The hook already shares `WORKFLOW_HINT` across client branches. The docs gate already pins to `EXPECTED_TOOLS` by identity.

## Decision
Do not generate skill/hook/prompt text from one template. Do not add a second tool allowlist. Leave per-surface wording; contract tests lock the required phrases.

## Alternatives considered
- Single generated guidance artifact: rejected; prompts, skill, and hook have different length and client constraints (S002 open question allowed per-client hook wording).
- Duplicate `EXPECTED_TOOLS` in the docs checker: already rejected by S001.

## Consequences
Guidance can drift in phrasing; tests fail only when required criteria disappear. Tool-surface drift is still caught by the S001 gate.
