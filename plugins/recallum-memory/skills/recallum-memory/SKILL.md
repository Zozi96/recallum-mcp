---
name: recallum-memory
description: Use Recallum at session start or resume, when historical project context is needed, when the user explicitly asks to recall or remember something, or after a durable preference, decision, constraint, or fact has been newly settled.
---

# Recallum Memory

Use the Recallum MCP server as concise, durable memory. Current user instructions and repository
instructions always override recalled memory.

## Tool Names

Recallum exposes five tools: `context`, `recall`, `remember`, `list_memories`, and `forget`. The
prefix differs by client, because Claude Code namespaces a plugin-bundled MCP server:

| Client | Prefix | Example |
| --- | --- | --- |
| Codex | `mcp__recallum__` | `mcp__recallum__context` |
| Claude Code | `mcp__plugin_recallum-memory_recallum__` | `mcp__plugin_recallum-memory_recallum__context` |

Use whichever prefix is actually present in your tool list; the session hook names the right one.
Below, tools are written unprefixed.

## Workflow

1. Use the opaque canonical project key supplied by the Recallum session hook. Without that
   context, hash the credential-free Git `origin`; if no origin exists, hash the repository root.
   Use global scope only for durable information that truly applies across projects.
2. At session start or resume, call `context` with `project`. Do this before planning when the tool
   is available.
3. When the user asks what was decided, preferred, constrained, remembered, or previously known,
   call `recall` with a focused query and `project`.
4. Apply relevant results only after checking them against current instructions and current
   repository evidence. Treat stale or conflicting memory as historical context, not authority.
5. After work settles a durable preference, decision, constraint, or fact, call `remember` once per
   atomic statement. Keep each statement short, self-contained, and useful in a later session. Do
   not store plans still under discussion, transient status, logs, full conversations, or
   information already captured unchanged.
6. Use `list_memories` only to browse or diagnose stored entries. Use `forget` only when the user
   requests removal or confirms that an entry is wrong or obsolete.

## Safety

- Ask before storing secrets, credentials, personal data, sensitive business information, or
  anything whose durability or intended scope is ambiguous.
- Never infer consent to preserve sensitive content from its appearance in a prompt or file.
- If Recallum is unavailable, continue the task without it and state the limitation only when it
  affects the result.

## Completion Criteria

- Relevant context was loaded or searched when a trigger applied.
- Recalled information was reconciled with current instructions and repository state.
- Each newly stored item is atomic, durable, correctly scoped, and non-sensitive or explicitly
  approved.
- No memory write was made when nothing durable was settled.
