## Context

Recallum stores atomic memories and builds session snapshots in `MemoryService.context` via `SessionContextBudget`: importance-ranked global + project pools, optional hybrid focus, then a shared item/char budget. Preferences and constraints lead only through **category order** (`preference` → `constraint` → `decision` → `fact`); they still compete with everything else for the same caps. High-volume project facts can crowd out durable always-on knowledge that is not semantically near the current `focus`.

Competitive products (SuperMemory profiles, Mem0 personalization) keep an always-on layer separate from search. Recallum’s product rule for this hardening wave is: **the agent decides writes; the system amplifies reads** — no new write tools, no server LLM extract in this change.

Today the MCP stack deliberately exposes **tools only**: `validate_only_tools_are_exposed` rejects resources/prompts because `BearerAuthMiddleware` authenticates `on_call_tool` alone. Any profile resource therefore requires auth coverage for resource reads first.

## Goals / Non-Goals

**Goals:**

- Materialize a **user-scoped** (and optional **project-scoped**) profile from existing active memories only.
- Rebuild on lifecycle writes that change eligibility; lazy rebuild on read if missing/stale.
- Make `context` always include the profile under a **reserved sub-budget** that focus/importance cannot steal.
- Expose profile for inspection (context payload + web GET; MCP resource only with authenticated resource access).
- Keep additive API shapes; zero new write tools; no chat LLM dependency.

**Non-Goals:**

- Entity graph, multi-hop recall boost, task-scoped memory, auto-extract, auto-forget, DERIVES.
- LLM-generated profile prose or summarized paraphrases (v1 uses **verbatim** memory content).
- Changing hybrid `recall` ranking (beyond marking served profile source memories as used if they appear in context).
- Expanding MCP with a `get_profile` tool (prefer resource + context enrichment).

## Decisions

### D1 — Profile is a projection, not a second knowledge base

**Choice:** Store a derived row (or one global + optional per-project rows) whose items are **pointers + denormalized content snapshots** of active memories selected by rules.

**Why:** Rebuild is cheap relative to re-ranking every session; clients can cache `content_hash` / `built_at`. Agents still correct truth via `update`/`merge`/`forget` on the underlying memory.

**Alternatives:** Pure on-read selection (no table) — simpler, but no stable digest for hooks and redoes full ranking every call. Separate free-text profile the user edits — second source of truth, rejected.

### D2 — Selection rules (v1, rule-based)

For a profile key `(user_id, project | null)`:

| Slice | Eligibility | Order | Cap (tunable limits) |
|-------|-------------|-------|----------------------|
| **static** | Active memories where `category ∈ {preference, constraint}` **or** `importance >= profile_static_min_importance` (default 8), visibility = global-only for the user-global profile; for a project profile, visibility = global + that project | importance desc, then `coalesce(reconfirmed_at, created_at)` desc, then id | `profile_static_max_items` (default 12), `profile_static_max_chars` (default 2000) |
| **dynamic** | Active memories in the same visibility **not already in static**, with recent **recall** signal: `last_recalled_at` within `profile_dynamic_window_days` (default 14). Creation alone does not qualify (would empty the category snapshot) | `last_recalled_at` desc, then created_at desc | `profile_dynamic_max_items` (default 8), `profile_dynamic_max_chars` (default 1500) |

- Superseded/retired rows never qualify.
- Content is stored **verbatim** (may be truncated with the same ellipsis rules as context when hitting char caps).
- `source_memory_ids` ordered as rendered; `content_hash` = stable hash of the canonical serialized slices.

**Why these rules:** Preferences/constraints are always-on by product language; high importance catches identity-like facts mis-tagged as `fact`/`decision`. Dynamic covers “what I’m working on lately” without a second LLM.

### D3 — Keys: user-global + optional project overlay

**Choice:**

- Always maintain a logical **user-global** profile (`project=None` at the API;
  stored as the empty-string key): globals only.
- When `context(project=P)` runs, ensure one **combined project profile** for `P`; its static/dynamic slices are selected from global memories plus that project only. Context and profile GET consume this single row.

**Assembly for `context(project=P)`:**

```
profile_block = profile_P.static + profile_P.dynamic (capped; static preferred)
```

Then remaining budget feeds today’s `SessionContextBudget.assemble` on importance + focus pools, **excluding ids already in the profile block** so they are not double-paid.

**Why:** Matches “who I am” and “this repo” while keeping the project read path one coherent materialized row.

### D4 — Rebuild triggers

Profile freshness uses a monotonic `users.memory_generation` counter rather
than timestamps. Content/eligibility mutations increment it in the same
transaction; context-count and embedding-only maintenance do not. A rebuild
captures the generation, then locks the user row and compares it during the
upsert. A mismatch causes a bounded CAS retry, preventing stale rebuilds from
overwriting newer mutations.

**Eager (same request, after successful mutation):** `remember` (create or reconfirm), `remember_batch` item success, `update` (in-place or supersede), `merge`, `forget`, and both source/target keys after project reassignment. Rebuild every profile key that the changed memory could affect:

- Always rebuild user-global and every existing project profile when the memory is global (or was a global source).
- Rebuild project profile for `memory.project` when scope is project; on forget/update of a project memory, that project key.

Recall usage updates also increment the generation so the dynamic slice becomes
stale; they rely on the next profile read instead of adding rebuild work to the
recall response.

**Lazy:** On `context` / profile GET, rebuild when no row exists or the row's
stored generation differs from `users.memory_generation`. The rebuild uses the
same bounded CAS loop described above; exhaustion degrades the profile read.

**Failure policy:** Rebuild failure MUST NOT fail the originating write; log and leave previous profile (or empty). Lazy rebuild failure → `context` falls back to today’s assembly without profile block and sets `profile.available=false`.

### D5 — `context` budget split

**Choice:** Introduce reserved profile budget from limits:

- `profile_context_max_items` / `profile_context_max_chars` (defaults aligned with static+dynamic caps).
- Caller `max_items` / `max_chars` apply to the **total** response; profile consumes first (up to its reserve), remainder goes to `SessionContextBudget`.
- If caller budget is smaller than the profile reserve, profile is truncated to the caller budget; groups still receive the remainder (possibly zero).
- Profile items appear in a first-class `profile` field on `ContextResult`, **not** mixed into category groups (avoids double-counting and keeps always-on visually separate for agents). Category groups remain the task/project snapshot as today, minus profile source ids.

**Why separate field:** SuperMemory-style always-on vs search; agents can render profile before groups; `omitted`/`total_available` stay about the full active set; document that profile items are also “served” for usage tracking.

### D6 — MCP: resource only with authenticated resource path

**Choice:**

1. Extend MCP auth so resource list/read requires the same Bearer API key as tools (middleware or FastMCP hooks equivalent to `on_call_tool`).
2. Keep `validate_only_tools_are_exposed` **or replace it** with `validate_resources_are_authenticated` that allows only known profile URIs and still forbids prompts until designed.
3. Register read-only resource e.g. `recallum://profile` and template `recallum://profile/{project}` returning the materialized profile JSON for the authenticated user.

**Why not a new tool:** Avoids tool-choice sprawl (explicit product constraint from explore). **Why not ship resource without auth fix:** Current middleware would make it unauthenticated — unacceptable.

**Fallback if auth extension slips:** Ship profile only via `context` + web GET; resource is a blocking task dependency, not optional for “done” if proposal requires it — implement auth first in tasks order.

### D7 — Persistence shape

**Choice:** Table `memory_profiles`:

| Column | Notes |
|--------|--------|
| `user_id` | FK, RLS |
| `project` | empty string = user-global; non-empty values are project keys |
| `static_items` | JSONB list of `{id, category, content, scope, project, importance, …}` |
| `dynamic_items` | same shape |
| `source_memory_ids` | UUID[] |
| `content_hash` | text |
| `built_at` | timestamptz |
| `generation` | user mutation generation captured by the CAS rebuild |
| primary key `(user_id, project)` | one row per key |

RLS: same forced user isolation pattern as `memories`.

### D8 — Web and plugin

- `GET /me/memory-profile` optional `?project=` → profile JSON; session identity only.
- Session bootstrap: no required hook change if `context` already embeds profile; optional digest rendering may prefer profile static lines first (skill/hook text tweak only if digest path parses `context` JSON — today digest is MCP `context` tool result).

### D9 — Surface freeze

**Net new write tools = 0.** Net new read tools = 0. Resources: profile only. No entity or task APIs in this change.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Profile duplicates content already in groups | Exclude profile source ids from importance/focus assembly |
| Stale profile after concurrent writes | Eager rebuild after mutations + generation CAS and lazy generation repair |
| Rebuild cost on every `remember` | Selection is SQL-limited top-N by importance/recency, not full table scan of content embeddings |
| Auth gap for MCP resources | Auth extension is a hard prerequisite task before registering resources |
| Small `max_chars` starves task snapshot | Document reserve defaults; clamp reserve to ≤ 40% of default context chars so remainder stays usable |
| Mis-tagged high-importance noise in static | Importance threshold 8 + category preference; user can lower importance or forget |
| Spec drift on MCP tool count (7 vs 9 tools) | Delta must not reassert obsolete “exactly seven tools”; only add resource requirements |

## Migration Plan

1. Add Alembic migration for `memory_profiles` + RLS policies matching memories isolation.
2. Deploy code that rebuilds on write and reads profile in `context` (empty profile until first rebuild).
3. Backfill: lazy rebuild on first `context` per user (no mandatory offline job).
4. Enable MCP resource after auth middleware covers resource methods.
5. Rollback: drop feature flags not required if deploy is single-version; rollback migration drops table; `context` without profile field breaks only new clients — keep `profile` optional with default empty for one release if needed. Prefer required `profile` object with `available: false` for schema stability.

## Open Questions

- Exact default for `profile_static_min_importance` (8 vs 7) — start at 8; tune with eval later.
- Whether project profile static should **re-include** global preferences or only project-local pins (assembly in D3 re-includes globals from user-global row — project row can store only project-scoped candidates to avoid duplication at rest).
- Digest hook: parse new `profile` field explicitly vs rely on groups alone — recommend explicit profile lines in digest renderer when present.
