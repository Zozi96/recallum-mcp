---
name: recallum-memory
description: Use Recallum at session start or resume, when historical project context is needed, when the user asks to recall or remember something, or after substantial work reveals verified reusable context that would save a future agent rediscovery, including preferences, decisions, constraints, architecture, terminology, workflows, commands, integration contracts, root causes, and recurring gotchas.
---

# Recallum Memory

Use the Recallum MCP server as concise, durable memory. Current user instructions and repository
instructions always override recalled memory.

## Tool Names

Recallum exposes fifteen tools: `context`, `recall`, `get_memory`, `remember`, `remember_batch`,
`update`, `merge_memories`, `list_memories`, `related_memories`, `reconfirm`, `forget`,
`save_skill`, `match_skills`, `get_skill`, and `forget_skill`. The last four store skills --
versioned procedures, a separate entity from memories (see "Skills vs Memories" below). The
prefix differs by client, because
Claude Code namespaces a plugin-bundled MCP server:

| Client | Prefix | Example |
| --- | --- | --- |
| Codex | `mcp__recallum__` | `mcp__recallum__context` |
| Claude Code (plugin) | `mcp__plugin_recallum-memory_recallum__` | `mcp__plugin_recallum-memory_recallum__context` |
| Claude Code (native / Desktop) | `mcp__recallum__` | `mcp__recallum__context` |
| Grok Build | `recallum__` | `recallum__context` (via `search_tool` / `use_tool`) |
| Cursor | Recallum MCP tools in Available Tools | the `context` tool in Available Tools |

Use whichever client tool names are actually present in your tool list; the session hook names the
forms that may apply. On Claude Code, **either** the plugin prefix or the native `mcp__recallum__`
prefix (installer dual-write for Desktop ToolSearch) may be present — use ToolSearch (`+recallum`
or `select:`) before concluding tools are missing. Cursor does not provide a stable textual tool
prefix, so use the names shown in Available Tools. Below, tools are written unprefixed.

## Skills vs Memories

A memory is an outcome or a lesson: what was decided, preferred, constrained, or learned. A skill
is a repeatable procedure with concrete steps: when this situation happens, follow this sequence.
If it is unsure which one applies, store it as a memory -- skills are for genuinely reusable
procedures, not every fact that happens to involve a sequence of actions.

Use `save_skill` when you have discovered or verified a multi-step procedure worth reusing: pass
`name`, `description`, `triggers` (when the procedure applies), `steps` (the ordered procedure),
and an optional `constraints` bullet list. Saving the same `name` in the same scope again with
identical steps is a no-op (`created=false`); different steps require `replace=true`, which
supersedes the active version and links it to what it replaced. Use `match_skills` -- not
`recall` -- to find a procedure by description or situation; `recall` searches memories only and
never returns skills. Use `get_skill` to fetch one skill's full triggers, steps, and constraints
by id, and `forget_skill` to retire one that no longer applies. Never derive a skill automatically
from a session or transcript; only save one when it is genuinely reusable and verified.

## Memory Language

Write every stored memory in English, and phrase every `recall` query in English, whatever language
the session speaks. This is not a style preference. Deduplication is an exact hash of the stored
content and the full-text index uses the English configuration, so one fact written once in Spanish
and once in English becomes two memories that no single query retrieves, and that exact dedup can
never collapse.

Both halves are required. Storing in English while still querying in the user's language is worse
than storing in that language: the full-text and trigram legs stop matching entirely and only the
semantic leg carries the search.

Keep verbatim whatever only means something as written — identifiers, commands, file paths, error
strings, and terms the user explicitly defined. A preference *about* another language is itself
stored in English: `User-facing documentation is written in Spanish`, not the Spanish sentence.
Translating an existing, still-true memory is not a reason to call `update`.

## Workflow

1. Use the opaque canonical project key supplied by the Recallum session hook. If the hook context
   is absent (including a Cursor session that drops `sessionStart` context), derive the same key
   exactly:
   - Resolve the workspace to its Git top-level. Use `origin`, or the first remote reported by
     `git remote` when `origin` is absent.
   - For a parseable URL or SCP-style remote, normalize to `<lowercase-host>/<path>` after removing
     leading/trailing path slashes and one trailing `.git`. SHA-256 hash that UTF-8 string, take the
     first 16 lowercase hex characters, and prefix `remote:`.
   - With no parseable remote, SHA-256 hash the absolute Git root (or absolute workspace when it is
     not a repository), take the first 12 lowercase hex characters, and prefix `local:`.
   The only scopes are `global` and `project`: use `global` only for durable information that truly
   applies across projects, such as a general user preference.
2. At session start or resume, call `context` with `project` — unless the session hook already
   injected the digest, in which case do not repeat the call. When the task is already known, pass
   it as `focus` (a short task summary): the snapshot then also includes memories relevant to that
   task. Do this before planning when the tool is available.
3. When the user asks what was decided, preferred, constrained, remembered, or previously known,
   call `recall` with a focused query and `project`. Also use `recall` whenever `context` reports
   `omitted > 0` and the omitted material could matter. Fetch the full text of items marked
   `content_truncated` with `get_memory` by id; passing `include_history` also returns the retired
   memories it replaced.
4. Apply relevant results only after checking them against current instructions and current
   repository evidence. Treat stale or conflicting memory as historical context, not authority.
   Use the freshness signals to judge: `reconfirmed_at` says when identical content was last
   re-stored, `last_recalled_at`/`recall_count` say whether the memory actually matches recall
   queries, and `context_count` how often it rode along in session snapshots. An
   old memory that was never reconfirmed deserves verification before being trusted; verifying one
   that is still true is a good moment to call `reconfirm`, which stamps `reconfirmed_at`. Context items flag
   this as `stale: true`, and `list_memories` with `stale=true` returns the full verification
   queue for the current scope.
5. After a useful `recall` or `context` hit, optionally call `related_memories` when exploring
thematic neighbourhood around a seed would help; do not call it on every recall. After
substantial work, run one capture scan: what newly verified context would save a future
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
   Optionally also set `kind`, a second facet orthogonal to category for coding work — choose
   both together, never `kind` instead of `category`:
   - `failure`: a bug, root cause, or broken approach.
   - `solution`: what fixed a failure.
   - `architecture`: how a system or component is structured.
   - `convention`: a naming, style, or structural rule to follow.
   - `todo`: a short-lived task, not a backlog — MUST also set `ttl_seconds`; a durable
     (TTL-less) `todo` is rejected.
   - `command`: a verified reusable command or workflow.
   Leave `kind` unset when nothing fits; unset is normal and a `kind` filter never matches it.
7. Call `remember` once per atomic statement, or `remember_batch` when the capture scan produced
   several (it applies the same rules per item and reports each outcome independently). Make each
   statement self-contained and specific enough to use without this conversation. Do not store
   plans still under discussion, guesses, transient status such as the current branch or worktree,
   temporary outages, logs, full conversations, source-code inventories, or information already
   captured unchanged.
8. Read the `similar` field on every `remember` and `remember_batch` outcome. It lists existing
   memories about the same subject — across every category, since a `fact` can contradict a
   `decision` — which are otherwise invisible: the response shows your new memory and nothing
   else. Similarity means the two are about the same thing, never that they agree. Read both and
   decide. When several active memories restate or refine one underlying claim, consolidate them
   with `merge_memories`: one consolidated statement, all sources retired and linked (recoverable
   via `get_memory` history). Never merge contradictions — verify which one is wrong, then
   `update` or `forget` it; the server never resolves similar memories for you.
9. When a stored fact has changed, call `update` with the new `content` instead of `forget` plus
   `remember`. That retires the old memory and links it to its replacement, so the correction is
   recoverable and the two never both look current. Passing only `importance`, `category`, or
   `metadata` edits in place and keeps the id. Scope and project cannot be changed.
10. Use `list_memories` only to browse or diagnose stored entries. In the stale queue
    (`stale=true`), verify each item with `get_memory` and end it with exactly one resolution:
    `reconfirm` when the claim is still true — prefer it over re-storing identical content —
    `update` when the fact changed, `forget` when the user requests removal or confirms the
    entry is wrong with nothing replacing it (if something replaces it, that is `update`), or
    `merge_memories` when it restates another active claim. Reviewing an item without concluding
    is not a resolution; every verified stale item ends in one of those four actions.
11. If the client supports MCP prompts, `session-start`, `capture-scan`, and `stale-review` are
shortcuts for the start, capture, and stale-review parts of this workflow.

## Mid-task retrieval checkpoints

Keep an ephemeral conceptual retrieval key for the active task:
`project + active objective + current subsystem/hypothesis/decision`. A checkpoint is warranted
only when that key changes materially and durable context could affect the next action. Positive
triggers include entering a new subsystem, replacing a causal hypothesis, or approaching a
sensitive security, data, compatibility, deployment, or public-interface decision when plausible
history may exist. Do not checkpoint merely because time passed, more tools ran, one isolated
failure occurred, or a `resume|clear|compact` digest already covers the active focus.

For a checkpoint, call `recall` with the canonical project key and a short English query that
describes the task delta, next decision, and identifiers verbatim. Start with `limit=3`; use a
scope or category filter only when the task makes it unambiguous. Keep an ephemeral set of
equivalent query keys and served memory ids: suppress an equivalent query and do not re-analyse a
memory already covered by the active context. If a later checkpoint would return the same ids,
skip it unless new evidence changes the active key. This state is not durable memory and need not be
persisted by the server.

If a checkpoint returns no applicable result, continue fail-open. Do not automatically increase
the limit or chain reformulated queries without new evidence. After `resume`, `clear`, or
`compact`, treat the injected digest as generic session context, not necessarily a task snapshot:
do not call `context` or `recall` again when it covers the active subsystem, hypothesis, or
decision; when it does not, make one focused recovery with `context(focus=...)` or a specific
`recall` before the dependent decision. If Recallum is unavailable, tell the user once and keep
working without blocking.

Before using any retrieved memory, reconcile it with current instructions and current repository
evidence. A stale, contradictory, or truncated memory is historical context until verified; fetch
truncated text with `get_memory` when needed, and let current code and instructions win over an
outdated memory. A memory that agrees with both can be applied without rediscovering its content.

This checkpoint policy is identical for Codex (`mcp__recallum__`), Claude Code
(`mcp__plugin_recallum-memory_recallum__*` and/or `mcp__recallum__*` via ToolSearch), Grok Build
(`recallum__` via `search_tool` / `use_tool`), and Cursor (the Recallum MCP tools listed in
Available Tools): only the tool discovery step differs.

## Delegation

- When delegating work to a subagent, include the canonical project key and the relevant recalled
  memories (or the context digest) directly in its prompt: subagents do not run the session hook
  and may not have the Recallum tools at all.
- Subagents do not write memories. They report durable findings back to the lead agent, which runs
  the single capture scan at the end and consolidates before storing — parallel writers create
  near-duplicate storms that exact dedup cannot catch.

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
- Every memory written and every `recall` query issued was in English, with identifiers, commands
  and user-defined terms left verbatim.
- Overlapping evidence was consolidated instead of stored as redundant memories.
- No memory write was made when nothing durable was settled.
- Delegated work carried the project key and relevant memories in the subagent prompt, and only the
  lead agent wrote memories.
