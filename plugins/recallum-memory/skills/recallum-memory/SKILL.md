---
name: recallum-memory
description: Use Recallum at session start or resume, when historical project context is needed, when the user asks to recall or remember something, or after substantial work reveals verified reusable context that would save a future agent rediscovery, including preferences, decisions, constraints, architecture, terminology, workflows, commands, integration contracts, root causes, and recurring gotchas.
---

# Recallum Memory

Use the Recallum MCP server as concise, durable memory. Current user instructions and repository
instructions always override recalled memory.

## Tool Names

Recallum exposes six tools: `context`, `recall`, `remember`, `update`, `list_memories`, and
`forget`. The prefix differs by client, because Claude Code namespaces a plugin-bundled MCP server:

| Client | Prefix | Example |
| --- | --- | --- |
| Codex | `mcp__recallum__` | `mcp__recallum__context` |
| Claude Code | `mcp__plugin_recallum-memory_recallum__` | `mcp__plugin_recallum-memory_recallum__context` |

Use whichever prefix is actually present in your tool list; the session hook names the right one.
Below, tools are written unprefixed.

## Workflow

1. Use the opaque canonical project key supplied by the Recallum session hook. Without that
   context, hash the credential-free Git `origin`; if no origin exists, hash the repository root.
   The only scopes are `global` and `project`: use `global` only for durable information that truly
   applies across projects, such as a general user preference.
2. At session start or resume, call `context` with `project`. Do this before planning when the tool
   is available.
3. When the user asks what was decided, preferred, constrained, remembered, or previously known,
   call `recall` with a focused query and `project`.
4. Apply relevant results only after checking them against current instructions and current
   repository evidence. Treat stale or conflicting memory as historical context, not authority.
5. After substantial work, run one capture scan: what newly verified context would save a future
   agent several minutes of rediscovery or prevent a likely mistake? Store only answers likely to
   remain true across sessions. Zero items is valid; prefer a few high-signal items over a recap,
   and do not split one underlying lesson into redundant memories. Collapse a rule, its cause, and
   its confirming evidence into one statement; a passing test is evidence, not a separate memory,
   unless the command itself is a reusable workflow.
6. Map each item to the existing categories:
   - `preference`: how the user or team wants work performed or presented.
   - `decision`: a settled choice and, when useful, its reason.
   - `constraint`: an invariant, hard requirement, compatibility limit, or prohibited approach.
   - `fact`: verified reusable context such as architecture, terminology, ownership, workflows,
     reusable commands that were verified, integration contracts, root causes, or recurring
     gotchas.
7. Call `remember` once per atomic statement. Make it self-contained and specific enough to use
   without this conversation. Do not store plans still under discussion, guesses, transient
   status such as the current branch or worktree, temporary outages, logs, full conversations,
   source-code inventories, or information already captured unchanged.
8. Read the `similar` field on every `remember` result. It lists existing memories about the same
   subject, which are otherwise invisible: the response shows your new memory and nothing else.
   Similarity means the two are about the same thing, never that they agree. Read both and decide.
9. When a stored fact has changed, call `update` with the new `content` instead of `forget` plus
   `remember`. That retires the old memory and links it to its replacement, so the correction is
   recoverable and the two never both look current. Passing only `importance`, `category`, or
   `metadata` edits in place and keeps the id. Scope and project cannot be changed.
10. Use `list_memories` only to browse or diagnose stored entries. Use `forget` only when the user
   requests removal or confirms an entry is wrong with nothing replacing it -- if something
   replaces it, that is `update`.

## Safety

- Ask before storing secrets, credentials, personal data, sensitive business information, or
  anything whose durability or intended scope is ambiguous.
- Never infer consent to preserve sensitive content from its appearance in a prompt or file.
- If Recallum is unavailable, continue the task without it and state the limitation only when it
  affects the result.

## Completion Criteria

- Relevant context was loaded or searched when a trigger applied.
- Recalled information was reconciled with current instructions and repository state.
- Substantial work ended with one brief capture scan for newly verified reusable context.
- Each newly stored item is atomic, durable, correctly scoped, and non-sensitive or explicitly
  approved.
- Overlapping evidence was consolidated instead of stored as redundant memories.
- No memory write was made when nothing durable was settled.
