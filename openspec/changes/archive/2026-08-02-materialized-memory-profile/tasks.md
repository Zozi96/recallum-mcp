## 1. Persistence and domain model

- [x] 1.1 Add Alembic migration for `memory_profiles` (user_id, logical optional project stored with an empty global key, static/dynamic JSONB, source_memory_ids, content_hash, built_at, unique per user+project) with RLS matching memories isolation
- [x] 1.2 Add SQLAlchemy model and repository methods: get profile by key, upsert profile, list keys to rebuild
- [x] 1.3 Add profile selection limits to `MemoryLimits` (static/dynamic max items/chars, min importance, dynamic window days, context reserve caps)
- [x] 1.4 Implement pure selection + hashing helpers (static/dynamic rules, verbatim truncate, content_hash) with unit tests

## 2. Rebuild service

- [x] 2.1 Implement `rebuild_profile(user_id, project=None)` loading eligible active memories under correct visibility and upserting the row
- [x] 2.2 Wire eager rebuild (best-effort, never fails the mutation) after `remember` / reconfirm, `remember_batch` item success, `update`, `merge`, and `forget` for affected keys
- [x] 2.3 Implement lazy rebuild on read when missing or its stored generation differs from the user's monotonic memory generation
- [x] 2.4 Unit tests: rebuild inclusion/exclusion, forget removes source, rebuild failure does not roll back remember

## 3. Context integration

- [x] 3.1 Extend `ContextResult` (and related schemas) with a `profile` block: available flag, built_at, content_hash, static/dynamic items
- [x] 3.2 Change `MemoryService.context` to load/rebuild profile, apply reserved budget first, exclude profile source ids from importance/focus assembly, track usage for profile items
- [x] 3.3 Adjust `SessionContextBudget` or wrapper so total max_items/max_chars account for profile consumption without letting focus evict profile
- [x] 3.4 Unit tests: profile present, focus does not drop profile, no duplicate ids in groups, degraded path when profile unavailable, usage recording

## 4. Web self-service

- [x] 4.1 Add `GET /me/memory-profile` with optional `project` query, session-derived identity only
- [x] 4.2 Integration or API tests for auth rejection and owner-only data

## 5. MCP auth and resource

- [x] 5.1 Extend Bearer auth so MCP resource list/read require a valid API key (same identity derivation as tools)
- [x] 5.2 Replace or update `validate_only_tools_are_exposed` to allow only the profile resource URI(s) and still forbid prompts and arbitrary resources
- [x] 5.3 Register read-only profile resource (global + project template) returning materialized profile JSON
- [x] 5.4 Ensure `context` tool response schema documents/includes the profile field; no new write tools
- [x] 5.5 Tests: unauthenticated resource denied; authenticated resource returns owner profile; tool list unchanged except resource presence

## 6. Session bootstrap digest

- [x] 6.1 Update digest rendering in the plugin hook to prefer profile static then dynamic lines when `context` JSON includes an available profile
- [x] 6.2 Keep fail-open and time budget; tests for profile-first ordering within digest char cap

## 7. Verification

- [x] 7.1 Run unit and relevant integration tests; fix regressions in context/MCP/web
- [x] 7.2 Manual smoke: remember preference → context shows profile; forget → profile rebuild drops it; MCP resource with key

## Review remediation (checked)

- [x] Add monotonic user/profile generations, migration 0012, transactional mutation bumps, and bounded CAS rebuild retries.
- [x] Materialize combined global+project rows, rebuild existing project keys after global changes, and eagerly repair reassignment source/target keys.
- [x] Bound static and recent-dynamic SQL candidates independently; use the public `ProfileItem` model and shared clipping helper.
- [x] Add regression coverage for low-importance recent dynamic candidates, project isolation/combined rows, lazy repair after failed eager rebuilds, reassignment, stale CAS, and forgotten-content protection.
- [x] Exercise authenticated streamable-HTTP MCP resources and web profile isolation, profile RLS/migration-head checks, digest caps, plugin socket cleanup, Ruff, OpenSpec validation, OpenAPI regeneration, and full test suites.
