# Recallum

Recallum provides private, persistent memory for coding agents while keeping each user's knowledge isolated and intentionally scoped.

## Language

**Memory**:
An atomic, self-contained preference, decision, constraint, or fact owned by one user.
_Avoid_: Note, record, entry

**Global Memory**:
A Memory visible across all of its owner's projects.
_Avoid_: Unscoped Memory, default Memory

**Project Memory**:
A Memory visible only within one named project belonging to its owner.
_Avoid_: Local Memory, scoped Memory

**Memory Visibility**:
The rule selecting which Global Memories and Project Memories are eligible for a read operation. A project view includes Global Memories plus that project's Project Memories unless explicitly narrowed.
_Avoid_: Filtering, access scope

**Session Context**:
A size-bounded, category-grouped selection of important Memories used to begin or resume an agent session.
_Avoid_: Context dump, bootstrap data

**User Identity**:
The owner established from a valid API key for an authenticated operation.
_Avoid_: Account, tenant

**Identity Administration**:
The user and API-key lifecycle used to create users and issue, list, or revoke their credentials.
_Avoid_: User management, key management
## Web identity

A web session is a browser credential stored independently from API keys. Only
its SHA-256 token hash is persisted; idle and absolute expirations bound its
lifetime, and rotation reuse revokes its successor chain. An administrator is a
user whose `is_admin` flag permits later administrative HTTP operations. It does
not grant access to another user's memories: content remains protected by forced
PostgreSQL RLS, while users, API keys, passwords, and web sessions are managed
through admin-scoped identity repositories outside that content boundary.

## Operational telemetry boundary

Memory content remains protected by forced PostgreSQL Row-Level Security.
Tool-usage telemetry is operational data and deliberately does not use RLS so
operators can aggregate it. Consequently, `tool_activity` may contain only
identity and operation metadata: tool name, project, timing, counts and
failure/degradation flags. Queries, memory content, tool arguments, result
fragments and any other user-authored text must never be added to that table.
Self-service activity reads enforce isolation with an explicit application-layer
`user_id` filter.
