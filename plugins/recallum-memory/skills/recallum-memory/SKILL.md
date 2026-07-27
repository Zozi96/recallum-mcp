---
name: recallum-memory
description: Use Recallum at session start or resume, when historical project context is needed, when the user explicitly asks to recall or remember something, or after a durable preference, decision, constraint, or fact has been newly settled.
---

# Recallum Memory

Use the Recallum MCP server as concise, durable memory. Current user instructions and repository
instructions always override recalled memory.

## Workflow

1. Use the opaque canonical project key supplied by the Recallum session hook. Without that
   context, hash the credential-free Git `origin`; if no origin exists, hash the repository root.
   Use global scope only for durable information that truly applies across projects.
2. At session start or resume, call `mcp__recallum__context` with `project`. Do this before planning
   when the tool is available.
3. When the user asks what was decided, preferred, constrained, remembered, or previously known,
   call `mcp__recallum__recall` with a focused query and `project`.
4. Apply relevant results only after checking them against current instructions and current
   repository evidence. Treat stale or conflicting memory as historical context, not authority.
5. After work settles a durable preference, decision, constraint, or fact, call
   `mcp__recallum__remember` once per atomic statement. Keep each statement short,
   self-contained, and useful in a later session. Do not store plans still under discussion,
   transient status, logs, full conversations, or information already captured unchanged.
6. Use `mcp__recallum__list_memories` only to browse or diagnose stored entries. Use
   `mcp__recallum__forget` only when the user requests removal or confirms that an entry is wrong
   or obsolete.

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
