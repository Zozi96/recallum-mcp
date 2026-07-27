# Graph Report - .  (2026-07-26)

## Corpus Check
- 23 files · ~45,691 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 710 nodes · 1368 edges · 39 communities (25 shown, 14 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 130 edges (avg confidence: 0.66)
- Token cost: 1,400 input · 1,900 output

## Community Hubs (Navigation)
- Settings and DI Container
- Identity and API Keys
- Database Models and Schemas
- Memory Service Interface
- Auth Middleware Tests
- Memory Repository Seam
- FastAPI Skill Reference
- MCP Tool Tests
- Repository Contract Suite
- In-Memory Test Adapters
- Deployment and Operations
- Memory Service Tests
- OpenSpec Skills
- Ollama Embeddings and Errors
- Domain Glossary
- Admin CLI Tests
- Structured Logging
- Database Integration Tests
- OPSX Commands
- Request Identity Scope
- Release Process
- Smoke Test Script
- Postgres Role Hardening
- Auth Package Init
- Database Package Init
- Repositories Package Init
- Embeddings Package Init
- Recallum Package Init
- MCP Package Init
- Postgres Backup Script
- Soft-Delete Purge Script
- Postgres Restore Script
- Contract Tests Init
- Frontend Serving
- Exception Base Type

## God Nodes (most connected - your core abstractions)
1. `Settings` - 33 edges
2. `build_test_container()` - 32 edges
3. `FakeEmbeddingClient` - 29 edges
4. `Container` - 26 edges
5. `MemoryService` - 26 edges
6. `FakeMemoryRepository` - 26 edges
7. `make_service()` - 26 edges
8. `MemoryRepositoryContract` - 23 edges
9. `create_app()` - 20 edges
10. `User` - 19 edges

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
- **Release Publication Flow** — _agents_skills_release_skill_baseline, _agents_skills_release_skill_version_drift, _agents_skills_release_skill_english_release_notes, _agents_skills_release_skill_gh_release_create [EXTRACTED 1.00]
- **Recallum MCP Tools** — readme_recallum_project, readme_mcp_tools, readme_mcp_server [EXTRACTED 1.00]
- **OpenSpec Workflow Commands** — _claude_commands_opsx_apply_opsx_apply, _claude_commands_opsx_archive_opsx_archive, _claude_commands_opsx_bulk_archive_opsx_bulk_archive, _claude_commands_opsx_explore_opsx_explore, _claude_commands_opsx_ff_opsx_ff, _claude_commands_opsx_new_opsx_new, _claude_commands_opsx_propose_opsx_propose, _claude_commands_opsx_sync_opsx_sync, _claude_commands_opsx_apply_openspec [EXTRACTED 1.00]
- **FastAPI Best Practices Framework** — _agents_skills_fastapi_skill_fastapi_skill, _agents_skills_fastapi_references_dependencies, _agents_skills_fastapi_references_other_tools, _agents_skills_fastapi_references_path_operations, _agents_skills_fastapi_references_pydantic, _agents_skills_fastapi_references_responses, _agents_skills_fastapi_references_streaming [EXTRACTED 1.00]
- **OpenSpec Skill Suite** — _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill, _claude_skills_openspec_explore_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_sync_specs_skill [EXTRACTED 1.00]
- **Change Lifecycle Workflow** — _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill [INFERRED 0.85]
- **build-agent-memory-service OpenSpec change** — openspec_changes_build_agent_memory_service_proposal, openspec_changes_build_agent_memory_service_design, openspec_changes_build_agent_memory_service_tasks, openspec_changes_build_agent_memory_service_specs_agent_memory_lifecycle_spec, openspec_changes_build_agent_memory_service_specs_agent_memory_retrieval_spec, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [EXTRACTED 1.00]
- **Recallum deployment stack** — deploy_docker_compose_recallum_service, deploy_docker_compose_postgres_service, deploy_docker_compose_ollama_service, deploy_docker_compose_migrate_service [EXTRACTED 1.00]
- **MCP client ecosystem** — docs_clients_codex, docs_clients_claude_code, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [INFERRED 0.95]

## Communities (39 total, 14 thin omitted)

### Community 0 - "Settings and DI Container"
Cohesion: 0.05
Nodes (64): APIRouter, ArgumentParser, AsyncEngine, BaseSettings, FastAPI, Namespace, CheckStatus, create_app() (+56 more)

### Community 1 - "Identity and API Keys"
Cohesion: 0.06
Nodes (44): async_sessionmaker, AsyncSession, ApiKeyService, hash_token(), IssuedKey, IssuedUserKey, _normalize_email(), UUID (+36 more)

### Community 2 - "Database Models and Schemas"
Cohesion: 0.05
Nodes (51): Connection, datetime, DeclarativeBase, Base, Declarative metadata root. Alembic migrations target ``Base.metadata``.  The app, Shared declarative base for all Recallum models., SQLAlchemy declarative models mirroring the Alembic-owned schema.  The applicati, PostgreSQL repository for memories: create, fetch, list, search, soft-delete. (+43 more)

### Community 3 - "Memory Service Interface"
Cohesion: 0.06
Nodes (38): Category, ForgetResult, ListResult, MemoryOut, MemoryRepository, OllamaEmbeddingClient, RecallResult, AuthSettings (+30 more)

### Community 4 - "Auth Middleware Tests"
Cohesion: 0.08
Nodes (32): ApiKeyRepository, ApiKeyService, Identity, Middleware, MiddlewareContext, BearerAuthMiddleware, _extract_bearer(), Any (+24 more)

### Community 5 - "Memory Repository Seam"
Cohesion: 0.08
Nodes (25): Protocol, Memory, An atomic memory: preference, decision, constraint, or fact., MemoryRepository, Any, UUID, Return a page of active memories plus the total matching count., Nearest neighbours by cosine similarity (1 - distance). (+17 more)

### Community 6 - "FastAPI Skill Reference"
Cohesion: 0.06
Nodes (37): Dependency Injection Reference, Class Dependencies, Yield Scope, Other Tools Reference, Asyncer, HTTPX, Ruff, SQLModel (+29 more)

### Community 7 - "MCP Tool Tests"
Cohesion: 0.10
Nodes (29): Client, Exception, FastMCP, Names of the registered tools (used by tests)., Fail fast if the server exposes resources or prompts.      ``BearerAuthMiddlewar, tool_names(), validate_only_tools_are_exposed(), _exploding_server() (+21 more)

### Community 8 - "Repository Contract Suite"
Cohesion: 0.16
Nodes (11): MemoryVisibility, _embedding(), _hash(), MemoryRepositoryContract, Any, One contract, run against every MemoryRepository adapter.  Subclasses provide th, # NOTE: the id-ascending tiebreak (equal importance AND equal, Async test methods exercising the MemoryRepository contract. (+3 more)

### Community 9 - "In-Memory Test Adapters"
Cohesion: 0.13
Nodes (11): ApiKey, _cosine(), FakeApiKeyRepository, FakeMemoryRepository, Memory, ScoredMemory, UUID, Dict-backed repository implementing the real interface. (+3 more)

### Community 10 - "Deployment and Operations"
Cohesion: 0.10
Nodes (32): docker-compose.yml (local stack), migrate service (Alembic job), ollama service, postgres service (pgvector:pg17), recallum service, dokploy-compose.yml (Dokploy stack), Clients (Codex & Claude Code MCP config), Claude Code (MCP client) (+24 more)

### Community 11 - "Memory Service Tests"
Cohesion: 0.11
Nodes (28): Returns preset vectors per exact text; unknown texts raise., ScriptedEmbeddingClient, make_service(), ScoredMemory, Memory service unit tests with repository/embedding overrides (task 3.7)., F1: recall used to prefer the oldest memory on an equal RRF score., _scored(), test_context_checks_budget_across_categories() (+20 more)

### Community 12 - "OpenSpec Skills"
Cohesion: 0.10
Nodes (27): openspec-apply-change Skill, OpenSpec CLI, OpenSpec Store, openspec-archive-change Skill, Archive Operation, openspec-bulk-archive-change Skill, Spec Conflict Resolution, openspec-explore Skill (+19 more)

### Community 13 - "Ollama Embeddings and Errors"
Cohesion: 0.12
Nodes (13): AsyncClient, F, EmbeddingError, OllamaEmbeddingClient, Exception, Ollama embedding client with bounded timeouts and bounded errors., Calls the local Ollama ``/api/embed`` endpoint synchronously per text.      Memo, Return the embedding vector for ``text`` or raise ``EmbeddingError``. (+5 more)

### Community 14 - "Domain Glossary"
Cohesion: 0.16
Nodes (16): Global Memory, Identity Administration, Memory, Memory Visibility, Project Memory, Session Context, User Identity, Atomic Memories (+8 more)

### Community 15 - "Admin CLI Tests"
Cohesion: 0.29
Nodes (13): build_test_container(), Any, A container fully isolated from PostgreSQL and Ollama., parse(), CLI (Identity Administration) unit tests: parser + `_run` dispatch., test_create_user_duplicate_raises_value_error_uncaught(), test_create_user_success_normalizes_email_and_persists(), test_issue_key_success_shows_plaintext_exactly_once() (+5 more)

### Community 16 - "Structured Logging"
Cohesion: 0.24
Nodes (8): LogRecord, JsonFormatter, Structured JSON logging with redaction of secrets.  Nothing here ever logs memor, Replace anything that looks like a credential with ``[REDACTED]``., Single-line JSON records with redaction applied to the rendered message., Install JSON structured logging on the root logger., redact(), setup_logging()

### Community 17 - "Database Integration Tests"
Cohesion: 0.29
Nodes (6): _make_user_with_key(), UUID, Integration tests against real PostgreSQL+pgvector (task 2.6).  A disposable con, test_deduplication_returns_existing_memory(), test_forget_excludes_from_all_queries(), test_isolation_between_two_users()

### Community 18 - "OPSX Commands"
Cohesion: 0.36
Nodes (9): OpenSpec, OPSX Apply, OPSX Archive, OPSX Bulk Archive, OPSX Explore, OPSX Fast Forward, OPSX New, OPSX Propose (+1 more)

### Community 19 - "Request Identity Scope"
Cohesion: 0.32
Nodes (7): Identity, identity_scope(), Request-scoped identity derived from the authenticated API key.  The FastMCP aut, The authenticated principal for one request., Bind ``identity`` for the duration of the wrapped call., Return the current identity or fail closed when absent., require_identity()

### Community 20 - "Release Process"
Cohesion: 0.33
Nodes (7): Release Baseline (last tag), English Release Notes, gh release create (tag + publish), Release Process Skill, Stale Local Tags, Version Drift, recallum

## Knowledge Gaps
- **35 isolated node(s):** `10-secure-runtime-role.sh script`, `backup_pg.sh script`, `purge_deleted.sh script`, `restore_pg.sh script`, `MCP Tools` (+30 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pydantic Reference` connect `FastAPI Skill Reference` to `Settings and DI Container`, `Database Models and Schemas`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Why does `MemoryService` connect `Memory Service Interface` to `Settings and DI Container`, `Database Models and Schemas`, `Memory Service Tests`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Container` connect `Settings and DI Container` to `Memory Service Interface`, `Auth Middleware Tests`, `In-Memory Test Adapters`, `Memory Service Tests`, `Admin CLI Tests`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 14 inferred relationships involving `Settings` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Settings` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `FakeEmbeddingClient` (e.g. with `Settings` and `Container`) actually correct?**
  _`FakeEmbeddingClient` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Container` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Container` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `MemoryService` (e.g. with `Container` and `SessionContextBudget`) actually correct?**
  _`MemoryService` has 3 INFERRED edges - model-reasoned connections that need verification._