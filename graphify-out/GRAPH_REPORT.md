# Graph Report - .  (2026-07-25)

## Corpus Check
- Corpus is ~41,318 words - fits in a single context window. You may not need a graph.

## Summary
- 564 nodes · 1187 edges · 38 communities (25 shown, 13 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 159 edges (avg confidence: 0.6)
- Token cost: 0 input · 12,966 output

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

## God Nodes (most connected - your core abstractions)
1. `MemoryService` - 36 edges
2. `Container` - 33 edges
3. `User` - 31 edges
4. `Settings` - 30 edges
5. `Memory` - 30 edges
6. `FakeEmbeddingClient` - 29 edges
7. `ApiKey` - 27 edges
8. `FakeMemoryRepository` - 26 edges
9. `make_service()` - 25 edges
10. `ApiKeyRepository` - 24 edges

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

## Communities (38 total, 13 thin omitted)

### Community 0 - "Ollama Embedding Client"
Cohesion: 0.07
Nodes (41): AsyncClient, Category, OllamaEmbeddingClient, Calls the local Ollama ``/api/embed`` endpoint synchronously per text.      Memo, Return the embedding vector for ``text`` or raise ``EmbeddingError``., Cheap readiness probe against Ollama's version endpoint., MemoryValidationError, ValueError (+33 more)

### Community 1 - "API Key Service"
Cohesion: 0.06
Nodes (38): Namespace, ApiKeyService, hash_token(), IssuedKey, IssuedUserKey, _normalize_email(), UUID, ValueError (+30 more)

### Community 2 - "Memory Domain & Repository"
Cohesion: 0.08
Nodes (26): Protocol, Memory, An atomic memory: preference, decision, constraint, or fact., MemoryRepository, Any, UUID, PostgreSQL repository for memories: create, fetch, list, search, soft-delete., Return a page of active memories plus the total matching count. (+18 more)

### Community 3 - "App Factory & Settings"
Cohesion: 0.09
Nodes (40): BaseSettings, Client, Exception, FastAPI, create_app(), Build the ASGI application with composed lifespans and the /mcp mount., Any, Top-level Recallum settings. (+32 more)

### Community 4 - "FastAPI Best Practices Skill"
Cohesion: 0.06
Nodes (36): Dependency Injection Reference, Class Dependencies, Yield Scope, Other Tools Reference, Asyncer, HTTPX, Ruff, SQLModel (+28 more)

### Community 5 - "Deployment & Operations"
Cohesion: 0.10
Nodes (32): docker-compose.yml (local stack), migrate service (Alembic job), ollama service, postgres service (pgvector:pg17), recallum service, dokploy-compose.yml (Dokploy stack), Clients (Codex & Claude Code MCP config), Claude Code (MCP client) (+24 more)

### Community 6 - "Memory Service Tests"
Cohesion: 0.11
Nodes (27): Returns preset vectors per exact text; unknown texts raise., ScriptedEmbeddingClient, make_service(), Memory service unit tests with repository/embedding overrides (task 3.7)., test_context_checks_budget_across_categories(), test_context_groups_by_category_and_truncates(), test_context_never_exceeds_max_chars(), test_context_without_project_returns_only_global() (+19 more)

### Community 7 - "OpenSpec Skills"
Cohesion: 0.10
Nodes (27): openspec-apply-change Skill, OpenSpec CLI, OpenSpec Store, openspec-archive-change Skill, Archive Operation, openspec-bulk-archive-change Skill, Spec Conflict Resolution, openspec-explore Skill (+19 more)

### Community 8 - "Auth Persistence & Wiring"
Cohesion: 0.14
Nodes (13): API key lifecycle: generation with cryptographic entropy, SHA-256 storage, singl, Dependency Injector wiring: concrete providers, app-scoped engine, test override, SQLAlchemy declarative models mirroring the Alembic-owned schema.  The applicati, ApiKeyRepository, UUID, Repository for API keys: hash-only persistence, lookup, revocation., Key storage and the pre-authentication hash lookup.      Runs in admin sessions:, Best-effort last-used timestamp. (+5 more)

### Community 9 - "Database Readiness"
Cohesion: 0.12
Nodes (17): AsyncEngine, DatabaseReadiness, Deep database-readiness module for schema and runtime-role safety., Own the PostgreSQL readiness policy behind one boolean interface., Return False for unavailable, incomplete, or unsafe databases., _docker_available(), _free_port(), _make_user_with_key() (+9 more)

### Community 10 - "Identity & Auth Middleware"
Cohesion: 0.14
Nodes (16): Middleware, MiddlewareContext, Identity, identity_scope(), Request-scoped identity derived from the authenticated API key.  The FastMCP aut, The authenticated principal for one request., Bind ``identity`` for the duration of the wrapped call., Return the current identity or fail closed when absent. (+8 more)

### Community 11 - "MCP Server & Health"
Cohesion: 0.15
Nodes (16): FastMCP, CheckStatus, LivenessResponse, BaseModel, FastAPI application factory.  FastAPI hosts operational endpoints (liveness/read, Liveness never touches dependencies., One readiness probe result, free of sensitive details., ReadinessResponse (+8 more)

### Community 12 - "Admin CLI & Config"
Cohesion: 0.20
Nodes (14): ArgumentParser, build_parser(), main(), Minimal stdlib admin CLI: create users, issue API keys, revoke keys.  The CLI ta, get_settings(), Validated application settings, loaded from environment variables.  Environment, Return the cached application settings., Container (+6 more)

### Community 13 - "Product Domain Concepts"
Cohesion: 0.16
Nodes (16): Global Memory, Identity Administration, Memory, Memory Visibility, Project Memory, Session Context, User Identity, Atomic Memories (+8 more)

### Community 14 - "Schema & Migrations"
Cohesion: 0.19
Nodes (11): Connection, DeclarativeBase, Base, Declarative metadata root. Alembic migrations target ``Base.metadata``.  The app, Shared declarative base for all Recallum models., do_run_migrations(), Alembic async environment: migrations are the only schema change path.  The data, Emit SQL without a live database connection. (+3 more)

### Community 15 - "User Management"
Cohesion: 0.20
Nodes (5): Raised when an email-based administration flow cannot resolve a user., UserNotFoundError, UUID, User CRUD used by the admin CLI and by key issuance., UserRepository

### Community 16 - "Structured Logging"
Cohesion: 0.24
Nodes (8): LogRecord, JsonFormatter, Structured JSON logging with redaction of secrets.  Nothing here ever logs memor, Replace anything that looks like a credential with ``[REDACTED]``., Single-line JSON records with redaction applied to the rendered message., Install JSON structured logging on the root logger., redact(), setup_logging()

### Community 17 - "OPSX Slash Commands"
Cohesion: 0.36
Nodes (9): OpenSpec, OPSX Apply, OPSX Archive, OPSX Bulk Archive, OPSX Explore, OPSX Fast Forward, OPSX New, OPSX Propose (+1 more)

### Community 18 - "Settings Models"
Cohesion: 0.22
Nodes (9): AuthSettings, DatabaseSettings, LimitsSettings, OllamaSettings, BaseModel, PostgreSQL connection settings., Local Ollama embedding service settings., API key authentication settings. (+1 more)

### Community 19 - "Session & Transactions"
Cohesion: 0.25
Nodes (5): async_sessionmaker, AsyncSession, UUID, Open a transaction scoped to ``user_id`` with RLS context set., Open a transaction without user context (admin/CLI paths only).

### Community 20 - "Health Router"
Cohesion: 0.67
Nodes (3): APIRouter, create_health_router(), Operational endpoints: /healthz and /readyz.

## Knowledge Gaps
- **35 isolated node(s):** `10-secure-runtime-role.sh script`, `recallum`, `backup_pg.sh script`, `purge_deleted.sh script`, `restore_pg.sh script` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pydantic Reference` connect `FastAPI Best Practices Skill` to `Ollama Embedding Client`, `MCP Server & Health`, `Admin CLI & Config`?**
  _High betweenness centrality (0.093) - this node is a cross-community bridge._
- **Why does `Container` connect `Admin CLI & Config` to `Ollama Embedding Client`, `API Key Service`, `Memory Domain & Repository`, `App Factory & Settings`, `Memory Service Tests`, `Auth Persistence & Wiring`, `Database Readiness`, `Identity & Auth Middleware`, `MCP Server & Health`, `User Management`, `Health Router`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Why does `MemoryService` connect `Ollama Embedding Client` to `Memory Domain & Repository`, `App Factory & Settings`, `Memory Service Tests`, `Auth Persistence & Wiring`, `Admin CLI & Config`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `MemoryService` (e.g. with `Container` and `Memory`) actually correct?**
  _`MemoryService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `Container` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Container` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `User` (e.g. with `ApiKeyService` and `IssuedKey`) actually correct?**
  _`User` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Settings` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Settings` has 12 INFERRED edges - model-reasoned connections that need verification._