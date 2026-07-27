# Graph Report - recallum  (2026-07-26)

## Corpus Check
- 99 files · ~45,130 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 702 nodes · 1540 edges · 53 communities (38 shown, 15 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 185 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `990f2f31`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ollama Embedding Client
- API Key Service
- Memory Domain & Repository
- App Factory & Settings
- FastAPI Best Practices Skill
- Deployment & Operations
- Memory Service Tests
- OpenSpec Skills
- Auth Persistence & Wiring
- Database Readiness
- Identity & Auth Middleware
- MCP Server & Health
- Admin CLI & Config
- Product Domain Concepts
- Schema & Migrations
- User Management
- Structured Logging
- OPSX Slash Commands
- Settings Models
- Session & Transactions
- Health Router
- Smoke Test Script
- Secure Runtime Role Script
- Auth Package
- Database Package
- Repositories Package
- Embeddings Package
- Recallum Package Root
- MCP Package
- Backup Script
- Purge Script
- Restore Script
- Frontend Serving
- Recallum Node
- Q: ¿Así está bien? Configuración Dockerfile en Dokploy
- Q: Dokploy build error: /recallum not found
- Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?
- .for_container
- Memory
- container.py
- User
- EmbeddingError
- FakeUserRepository
- test_api_keys.py
- OllamaEmbeddingClient
- fakes.py
- ApiKey
- _ExplodingMemoryService
- contract/__init__.py

## God Nodes (most connected - your core abstractions)
1. `MemoryService` - 38 edges
2. `Memory` - 37 edges
3. `FakeEmbeddingClient` - 34 edges
4. `Settings` - 33 edges
5. `Container` - 33 edges
6. `build_test_container()` - 32 edges
7. `User` - 31 edges
8. `FakeMemoryRepository` - 31 edges
9. `MemoryVisibility` - 30 edges
10. `ApiKey` - 27 edges

## Surprising Connections (you probably didn't know these)
- `openspec-apply-change Skill` --semantically_similar_to--> `openspec-apply-change Skill (Codex)`  [INFERRED] [semantically similar]
  .claude/skills/openspec-apply-change/SKILL.md → .codex/skills/openspec-apply-change/SKILL.md
- `openspec-archive-change Skill` --semantically_similar_to--> `openspec-archive-change Skill (Codex)`  [INFERRED] [semantically similar]
  .claude/skills/openspec-archive-change/SKILL.md → .codex/skills/openspec-archive-change/SKILL.md
- `openspec-bulk-archive-change Skill` --semantically_similar_to--> `openspec-bulk-archive-change Skill (Codex)`  [INFERRED] [semantically similar]
  .claude/skills/openspec-bulk-archive-change/SKILL.md → .codex/skills/openspec-bulk-archive-change/SKILL.md
- `openspec-ff-change Skill` --semantically_similar_to--> `openspec-ff-change Skill (Codex)`  [INFERRED] [semantically similar]
  .claude/skills/openspec-ff-change/SKILL.md → .codex/skills/openspec-ff-change/SKILL.md
- `openspec-sync-specs Skill` --semantically_similar_to--> `openspec-sync-specs Skill (Codex)`  [INFERRED] [semantically similar]
  .claude/skills/openspec-sync-specs/SKILL.md → .codex/skills/openspec-sync-specs/SKILL.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Recallum MCP Tools** — readme_recallum_project, readme_mcp_tools, readme_mcp_server [EXTRACTED 1.00]
- **OpenSpec Workflow Commands** — _claude_commands_opsx_apply_opsx_apply, _claude_commands_opsx_archive_opsx_archive, _claude_commands_opsx_bulk_archive_opsx_bulk_archive, _claude_commands_opsx_explore_opsx_explore, _claude_commands_opsx_ff_opsx_ff, _claude_commands_opsx_new_opsx_new, _claude_commands_opsx_propose_opsx_propose, _claude_commands_opsx_sync_opsx_sync, _claude_commands_opsx_apply_openspec [EXTRACTED 1.00]
- **FastAPI Best Practices Framework** — _agents_skills_fastapi_skill_fastapi_skill, _agents_skills_fastapi_references_dependencies, _agents_skills_fastapi_references_other_tools, _agents_skills_fastapi_references_path_operations, _agents_skills_fastapi_references_pydantic, _agents_skills_fastapi_references_responses, _agents_skills_fastapi_references_streaming [EXTRACTED 1.00]
- **OpenSpec Skill Suite** — _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill, _claude_skills_openspec_explore_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_sync_specs_skill [EXTRACTED 1.00]
- **Change Lifecycle Workflow** — _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill [INFERRED 0.85]
- **build-agent-memory-service OpenSpec change** — openspec_changes_build_agent_memory_service_proposal, openspec_changes_build_agent_memory_service_design, openspec_changes_build_agent_memory_service_tasks, openspec_changes_build_agent_memory_service_specs_agent_memory_lifecycle_spec, openspec_changes_build_agent_memory_service_specs_agent_memory_retrieval_spec, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [EXTRACTED 1.00]
- **Recallum deployment stack** — deploy_docker_compose_recallum_service, deploy_docker_compose_postgres_service, deploy_docker_compose_ollama_service, deploy_docker_compose_migrate_service [EXTRACTED 1.00]
- **MCP client ecosystem** — docs_clients_codex, docs_clients_claude_code, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [INFERRED 0.95]

## Communities (53 total, 15 thin omitted)

### Community 0 - "Ollama Embedding Client"
Cohesion: 0.07
Nodes (50): Category, Session context assembly: dedup, group, and budget memories for a snapshot., Item- and char-budget rules for assembling a session context snapshot., Dedup, group by category and apply the budget to produce a snapshot., SessionContextBudget, MemoryValidationError, ValueError, Raised when a memory input violates a domain rule. (+42 more)

### Community 1 - "API Key Service"
Cohesion: 0.15
Nodes (11): ApiKeyService, _normalize_email(), UUID, ValueError, Resolve an email and return its key metadata., Raised when an email-based administration flow cannot resolve a user., Canonical normalization shared by every email administration flow., Identity administration module owning user and API-key workflows. (+3 more)

### Community 2 - "Memory Domain & Repository"
Cohesion: 0.09
Nodes (19): async_sessionmaker, AsyncSession, MemoryRepository, Any, UUID, Return a page of active memories plus the total matching count., Nearest neighbours by cosine similarity (1 - distance)., Full-text candidates ranked with ts_rank_cd over the simple tsvector. (+11 more)

### Community 3 - "App Factory & Settings"
Cohesion: 0.20
Nodes (15): BaseSettings, create_app(), Build the ASGI application with composed lifespans and the /mcp mount., Top-level Recallum settings., Settings, FakeDatabaseReadiness, FakeEngine, Async engine stand-in for readiness probes and shutdown tests. (+7 more)

### Community 4 - "FastAPI Best Practices Skill"
Cohesion: 0.06
Nodes (36): Dependency Injection Reference, Class Dependencies, Yield Scope, Other Tools Reference, Asyncer, HTTPX, Ruff, SQLModel (+28 more)

### Community 5 - "Deployment & Operations"
Cohesion: 0.10
Nodes (32): docker-compose.yml (local stack), migrate service (Alembic job), ollama service, postgres service (pgvector:pg17), recallum service, dokploy-compose.yml (Dokploy stack), Clients (Codex & Claude Code MCP config), Claude Code (MCP client) (+24 more)

### Community 6 - "Memory Service Tests"
Cohesion: 0.15
Nodes (24): make_service(), Memory service unit tests with repository/embedding overrides (task 3.7)., F1: recall used to prefer the oldest memory on an equal RRF score., test_context_checks_budget_across_categories(), test_context_groups_by_category_and_truncates(), test_context_never_exceeds_max_chars(), test_context_without_project_returns_only_global(), test_forget_own_then_foreign_indistinguishable() (+16 more)

### Community 7 - "OpenSpec Skills"
Cohesion: 0.10
Nodes (27): openspec-apply-change Skill, OpenSpec CLI, OpenSpec Store, openspec-archive-change Skill, Archive Operation, openspec-bulk-archive-change Skill, Spec Conflict Resolution, openspec-explore Skill (+19 more)

### Community 8 - "Auth Persistence & Wiring"
Cohesion: 0.12
Nodes (33): ArgumentParser, Namespace, build_parser(), main(), Minimal stdlib admin CLI: create users, issue API keys, revoke keys.  The CLI ta, _run(), get_settings(), Return the cached application settings. (+25 more)

### Community 9 - "Database Readiness"
Cohesion: 0.15
Nodes (12): AsyncEngine, DatabaseReadiness, Deep database-readiness module for schema and runtime-role safety., Own the PostgreSQL readiness policy behind one boolean interface., Return False for unavailable, incomplete, or unsafe databases., _make_user_with_key(), UUID, Integration tests against real PostgreSQL+pgvector (task 2.6).  A disposable con (+4 more)

### Community 10 - "Identity & Auth Middleware"
Cohesion: 0.17
Nodes (12): Middleware, MiddlewareContext, Identity, identity_scope(), The authenticated principal for one request., Bind ``identity`` for the duration of the wrapped call., BearerAuthMiddleware, _extract_bearer() (+4 more)

### Community 11 - "MCP Server & Health"
Cohesion: 0.17
Nodes (16): FastMCP, Request-scoped identity derived from the authenticated API key.  The FastMCP aut, Return the current identity or fail closed when absent., require_identity(), build_mcp_server(), FastMCP server exposing exactly five tools, none accepting a user id.  Identity, Fail fast (startup/tests) if any tool schema ever grows a user selector., Names of the registered tools (used by tests). (+8 more)

### Community 12 - "Admin CLI & Config"
Cohesion: 0.12
Nodes (20): AuthSettings, DatabaseSettings, OllamaSettings, BaseModel, Validated application settings, loaded from environment variables.  Environment, PostgreSQL connection settings., Local Ollama embedding service settings., API key authentication settings. (+12 more)

### Community 13 - "Product Domain Concepts"
Cohesion: 0.16
Nodes (16): Global Memory, Identity Administration, Memory, Memory Visibility, Project Memory, Session Context, User Identity, Atomic Memories (+8 more)

### Community 14 - "Schema & Migrations"
Cohesion: 0.19
Nodes (11): Connection, DeclarativeBase, Base, Declarative metadata root. Alembic migrations target ``Base.metadata``.  The app, Shared declarative base for all Recallum models., do_run_migrations(), Alembic async environment: migrations are the only schema change path.  The data, Emit SQL without a live database connection. (+3 more)

### Community 15 - "User Management"
Cohesion: 0.22
Nodes (18): Client, _exploding_server(), _free_port(), mcp_client(), MCP integration tests over real HTTP: discovery, auth states, isolation (4.5)., Serve a container whose memory module always raises ``exc``., forget had no handler before the middleware; it is covered now., EmbeddingError was only translated in remember before the middleware. (+10 more)

### Community 16 - "Structured Logging"
Cohesion: 0.24
Nodes (8): LogRecord, JsonFormatter, Structured JSON logging with redaction of secrets.  Nothing here ever logs memor, Replace anything that looks like a credential with ``[REDACTED]``., Single-line JSON records with redaction applied to the rendered message., Install JSON structured logging on the root logger., redact(), setup_logging()

### Community 17 - "OPSX Slash Commands"
Cohesion: 0.36
Nodes (9): OpenSpec, OPSX Apply, OPSX Archive, OPSX Bulk Archive, OPSX Explore, OPSX Fast Forward, OPSX New, OPSX Propose (+1 more)

### Community 18 - "Settings Models"
Cohesion: 0.09
Nodes (19): Protocol, MemoryVisibility, Stable interface for memory-domain errors and visibility policy., Canonical owner-relative visibility shared by repository adapters., Apply the canonical policy in an in-memory adapter., _VisibleMemory, _embedding(), _hash() (+11 more)

### Community 19 - "Session & Transactions"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Okay ¿cuáles son las variables de entorno que hay que colocar?, Source Nodes

### Community 20 - "Health Router"
Cohesion: 0.21
Nodes (13): APIRouter, FastAPI, CheckStatus, create_health_router(), LivenessResponse, BaseModel, FastAPI application factory.  FastAPI hosts operational endpoints (liveness/read, Liveness never touches dependencies. (+5 more)

### Community 38 - "Q: ¿Así está bien? Configuración Dockerfile en Dokploy"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: ¿Así está bien? Configuración Dockerfile en Dokploy, Source Nodes

### Community 39 - "Q: Dokploy build error: /recallum not found"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Dokploy build error: /recallum not found, Source Nodes

### Community 40 - "Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?, Source Nodes

### Community 42 - "Memory"
Cohesion: 0.22
Nodes (8): Memory, An atomic memory: preference, decision, constraint, or fact., A memory row plus a per-signal score (cosine similarity or text rank)., ScoredMemory, FakeMemoryRepository, Any, UUID, Dict-backed repository implementing the real interface.

### Community 43 - "container.py"
Cohesion: 0.15
Nodes (10): FastMCP middleware enforcing ``Authorization: Bearer`` on every tool call., Dependency Injector wiring: concrete providers, app-scoped engine, test override, ApiKeyRepository, UUID, Repository for API keys: hash-only persistence, lookup, revocation., Key storage and the pre-authentication hash lookup.      Runs in admin sessions:, Resolve a bearer token hash to a non-revoked key and its user., Best-effort last-used timestamp. (+2 more)

### Community 44 - "User"
Cohesion: 0.20
Nodes (13): IssuedKey, IssuedUserKey, API key lifecycle: generation with cryptographic entropy, SHA-256 storage, singl, A freshly issued key. ``plaintext`` is shown once and never persisted., A freshly issued key together with its resolved user., Resolved user and key metadata for an administrative listing., UserKeys, A human owner of memories. Identified by API keys, never by agents. (+5 more)

### Community 45 - "EmbeddingError"
Cohesion: 0.14
Nodes (10): F, EmbeddingError, Exception, Ollama embedding client with bounded timeouts and bounded errors., Raised when Ollama cannot produce an embedding for a text., One translation point from domain errors to ``ToolError``.  Applied as a decorat, Translate memory-domain errors raised by a tool into ``ToolError``., translates_domain_errors() (+2 more)

### Community 46 - "FakeUserRepository"
Cohesion: 0.20
Nodes (9): FakeUserRepository, CountingApiKeyRepository, _issue(), Counts writes so the authentication hot path can be measured., F4: last_used_at used to be written on every single tool call., test_authentication_refreshes_last_used_once_per_interval(), test_authentication_refreshes_last_used_once_the_interval_elapses(), test_authentication_still_rejects_invalid_and_revoked_keys_without_writing() (+1 more)

### Community 47 - "test_api_keys.py"
Cohesion: 0.25
Nodes (13): hash_token(), SHA-256 hex digest of a raw bearer token., make_service(), API key lifecycle unit tests (task 4.1)., test_authenticate_valid_invalid_revoked(), test_create_user_normalizes_and_rejects_case_insensitive_duplicates(), test_create_user_rejects_invalid_email(), test_email_administration_flows_resolve_users_and_missing_policy() (+5 more)

### Community 48 - "OllamaEmbeddingClient"
Cohesion: 0.22
Nodes (5): AsyncClient, OllamaEmbeddingClient, Calls the local Ollama ``/api/embed`` endpoint synchronously per text.      Memo, Return the embedding vector for ``text`` or raise ``EmbeddingError``., Cheap readiness probe against Ollama's version endpoint.

### Community 49 - "fakes.py"
Cohesion: 0.28
Nodes (6): datetime, SQLAlchemy declarative models mirroring the Alembic-owned schema.  The applicati, PostgreSQL repository for memories: create, fetch, list, search, soft-delete., _cosine(), In-memory fakes isolating PostgreSQL and Ollama for unit tests., _scored()

### Community 50 - "ApiKey"
Cohesion: 0.31
Nodes (3): ApiKey, A revocable bearer credential. Only the SHA-256 hash is persisted., FakeApiKeyRepository

### Community 51 - "_ExplodingMemoryService"
Cohesion: 0.22
Nodes (3): _ExplodingMemoryService, Exception, Stands in for the memory module so any tool raises a chosen domain error.

## Knowledge Gaps
- **47 isolated node(s):** `10-secure-runtime-role.sh script`, `recallum`, `backup_pg.sh script`, `purge_deleted.sh script`, `restore_pg.sh script` (+42 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `docker-compose.yml (local stack)` (2× useful, score=1.99974775)
- `recallum service` (2× useful, score=1.99974775)
- `Operations runbook` (2× useful, score=1.99974775)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pydantic Reference` connect `FastAPI Best Practices Skill` to `Ollama Embedding Client`, `Health Router`, `Admin CLI & Config`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `Container` connect `Health Router` to `Ollama Embedding Client`, `API Key Service`, `Memory Domain & Repository`, `App Factory & Settings`, `Auth Persistence & Wiring`, `Database Readiness`, `Identity & Auth Middleware`, `container.py`, `User`, `MCP Server & Health`, `Admin CLI & Config`, `Memory`, `OllamaEmbeddingClient`, `fakes.py`, `ApiKey`, `FakeUserRepository`, `EmbeddingError`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `MemoryVisibility` connect `Settings Models` to `Ollama Embedding Client`, `fakes.py`, `Memory Domain & Repository`, `Memory`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `MemoryService` (e.g. with `Container` and `Memory`) actually correct?**
  _`MemoryService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Memory` (e.g. with `Base` and `MemoryRepository`) actually correct?**
  _`Memory` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `FakeEmbeddingClient` (e.g. with `Settings` and `Container`) actually correct?**
  _`FakeEmbeddingClient` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `Settings` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Settings` has 14 INFERRED edges - model-reasoned connections that need verification._