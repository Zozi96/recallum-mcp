# Graph Report - recallum  (2026-07-26)

## Corpus Check
- 112 files · ~52,518 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 820 nodes · 1758 edges · 57 communities (41 shown, 16 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 185 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `cfdbacb3`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- SessionContextBudget
- Container
- recallum_hook.py
- marketplace.json
- install.sh
- Recallum Setup
- AuthSettings
- Q: Okay ¿cuáles son las variables de entorno que hay que colocar?
- Q: ¿Así está bien? Configuración Dockerfile en Dokploy
- Q: Dokploy build error: /recallum not found
- Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?
- Recallum Memory
- .for_container
- conftest.py
- build_mcp_server
- .mcp.json
- OllamaEmbeddingClient
- errors.py

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
- **Release Publication Flow** — _agents_skills_release_skill_baseline, _agents_skills_release_skill_version_drift, _agents_skills_release_skill_english_release_notes, _agents_skills_release_skill_gh_release_create [EXTRACTED 1.00]
- **Recallum MCP Tools** — readme_recallum_project, readme_mcp_tools, readme_mcp_server [EXTRACTED 1.00]
- **OpenSpec Workflow Commands** — _claude_commands_opsx_apply_opsx_apply, _claude_commands_opsx_archive_opsx_archive, _claude_commands_opsx_bulk_archive_opsx_bulk_archive, _claude_commands_opsx_explore_opsx_explore, _claude_commands_opsx_ff_opsx_ff, _claude_commands_opsx_new_opsx_new, _claude_commands_opsx_propose_opsx_propose, _claude_commands_opsx_sync_opsx_sync, _claude_commands_opsx_apply_openspec [EXTRACTED 1.00]
- **FastAPI Best Practices Framework** — _agents_skills_fastapi_skill_fastapi_skill, _agents_skills_fastapi_references_dependencies, _agents_skills_fastapi_references_other_tools, _agents_skills_fastapi_references_path_operations, _agents_skills_fastapi_references_pydantic, _agents_skills_fastapi_references_responses, _agents_skills_fastapi_references_streaming [EXTRACTED 1.00]
- **OpenSpec Skill Suite** — _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill, _claude_skills_openspec_explore_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_sync_specs_skill [EXTRACTED 1.00]
- **Change Lifecycle Workflow** — _claude_skills_openspec_new_change_skill, _claude_skills_openspec_propose_skill, _claude_skills_openspec_ff_change_skill, _claude_skills_openspec_apply_change_skill, _claude_skills_openspec_archive_change_skill, _claude_skills_openspec_bulk_archive_change_skill [INFERRED 0.85]
- **build-agent-memory-service OpenSpec change** — openspec_changes_build_agent_memory_service_proposal, openspec_changes_build_agent_memory_service_design, openspec_changes_build_agent_memory_service_tasks, openspec_changes_build_agent_memory_service_specs_agent_memory_lifecycle_spec, openspec_changes_build_agent_memory_service_specs_agent_memory_retrieval_spec, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [EXTRACTED 1.00]
- **Recallum deployment stack** — deploy_docker_compose_recallum_service, deploy_docker_compose_postgres_service, deploy_docker_compose_ollama_service, deploy_docker_compose_migrate_service [EXTRACTED 1.00]
- **MCP client ecosystem** — docs_clients_codex, docs_clients_claude_code, openspec_changes_build_agent_memory_service_specs_mcp_agent_integration_spec [INFERRED 0.95]

## Communities (57 total, 16 thin omitted)

### Community 0 - "Settings and DI Container"
Cohesion: 0.18
Nodes (15): BaseSettings, FastAPI, create_app(), Build the ASGI application with composed lifespans and the /mcp mount., Top-level Recallum settings., Settings, FakeDatabaseReadiness, FakeEngine (+7 more)

### Community 1 - "Identity and API Keys"
Cohesion: 0.12
Nodes (13): Category, MemoryValidationError, ValueError, Raised when a memory input violates a domain rule., Any, UUID, Hybrid retrieval with RRF fusion; degrades to textual on embed failure., Merge ranked candidate lists with RRF (k=60). (+5 more)

### Community 2 - "Database Models and Schemas"
Cohesion: 0.13
Nodes (24): FastMCP server exposing exactly five tools, none accepting a user id.  Identity, Session context assembly: dedup, group, and budget memories for a snapshot., Dedup, group by category and apply the budget to produce a snapshot., ContextGroup, ContextItem, ContextResult, ForgetResult, ListResult (+16 more)

### Community 3 - "Memory Service Interface"
Cohesion: 0.06
Nodes (46): Connection, DeclarativeBase, ApiKeyService, IssuedKey, IssuedUserKey, _normalize_email(), UUID, ValueError (+38 more)

### Community 4 - "Auth Middleware Tests"
Cohesion: 0.07
Nodes (39): datetime, Middleware, MiddlewareContext, hash_token(), SHA-256 hex digest of a raw bearer token., Identity, identity_scope(), Request-scoped identity derived from the authenticated API key.  The FastMCP aut (+31 more)

### Community 5 - "Memory Repository Seam"
Cohesion: 0.09
Nodes (11): CompletedProcess, ClaudeInstallerTests, CodexInstallerTests, HookTests, InstallerTestCase, ManifestTests, Path, Pin the prefix to its inputs so a rename cannot silently break it.          Clau (+3 more)

### Community 6 - "FastAPI Skill Reference"
Cohesion: 0.07
Nodes (29): Dependency Injection Reference, Class Dependencies, Yield Scope, Other Tools Reference, Asyncer, HTTPX, Ruff, SQLModel (+21 more)

### Community 7 - "MCP Tool Tests"
Cohesion: 0.16
Nodes (24): Client, FastMCP, build_mcp_server(), Names of the registered tools (used by tests)., Fail fast if the server exposes resources or prompts.      ``BearerAuthMiddlewar, Create the FastMCP server wired to the given DI container., tool_names(), validate_only_tools_are_exposed() (+16 more)

### Community 8 - "Repository Contract Suite"
Cohesion: 0.12
Nodes (16): Protocol, MemoryVisibility, Stable interface for memory-domain errors and visibility policy., Canonical owner-relative visibility shared by repository adapters., Apply the canonical policy in an in-memory adapter., _VisibleMemory, _embedding(), _hash() (+8 more)

### Community 9 - "In-Memory Test Adapters"
Cohesion: 0.06
Nodes (33): async_sessionmaker, AsyncSession, Memory, An atomic memory: preference, decision, constraint, or fact., MemoryRepository, Any, UUID, PostgreSQL repository for memories: create, fetch, list, search, soft-delete. (+25 more)

### Community 10 - "Deployment and Operations"
Cohesion: 0.10
Nodes (32): docker-compose.yml (local stack), migrate service (Alembic job), ollama service, postgres service (pgvector:pg17), recallum service, dokploy-compose.yml (Dokploy stack), Clients (Codex & Claude Code MCP config), Claude Code (MCP client) (+24 more)

### Community 11 - "Memory Service Tests"
Cohesion: 0.12
Nodes (27): Returns preset vectors per exact text; unknown texts raise., ScriptedEmbeddingClient, make_service(), Memory service unit tests with repository/embedding overrides (task 3.7)., F1: recall used to prefer the oldest memory on an equal RRF score., _scored(), test_context_checks_budget_across_categories(), test_context_groups_by_category_and_truncates() (+19 more)

### Community 12 - "OpenSpec Skills"
Cohesion: 0.10
Nodes (27): openspec-apply-change Skill, OpenSpec CLI, OpenSpec Store, openspec-archive-change Skill, Archive Operation, openspec-bulk-archive-change Skill, Spec Conflict Resolution, openspec-explore Skill (+19 more)

### Community 13 - "Ollama Embeddings and Errors"
Cohesion: 0.33
Nodes (12): Item- and char-budget rules for assembling a session context snapshot., SessionContextBudget, flatten(), memory(), Session Context budget rules, exercised directly with no service or repository., F2: an item that does not fit no longer abandons the rest of its category., test_a_short_memory_after_an_oversized_one_is_still_kept(), test_char_budget_is_never_exceeded() (+4 more)

### Community 14 - "Domain Glossary"
Cohesion: 0.16
Nodes (16): Global Memory, Identity Administration, Memory, Memory Visibility, Project Memory, Session Context, User Identity, Atomic Memories (+8 more)

### Community 15 - "Admin CLI Tests"
Cohesion: 0.24
Nodes (19): ArgumentParser, Namespace, build_parser(), _run(), build_test_container(), Any, A container fully isolated from PostgreSQL and Ollama., test_cli_email_workflows_preserve_output_and_codes() (+11 more)

### Community 16 - "Structured Logging"
Cohesion: 0.24
Nodes (8): LogRecord, JsonFormatter, Structured JSON logging with redaction of secrets.  Nothing here ever logs memor, Replace anything that looks like a credential with ``[REDACTED]``., Single-line JSON records with redaction applied to the rendered message., Install JSON structured logging on the root logger., redact(), setup_logging()

### Community 17 - "Database Integration Tests"
Cohesion: 0.14
Nodes (13): AsyncEngine, DatabaseReadiness, Deep database-readiness module for schema and runtime-role safety., Own the PostgreSQL readiness policy behind one boolean interface., Return False for unavailable, incomplete, or unsafe databases., _make_user_with_key(), UUID, Integration tests against real PostgreSQL+pgvector (task 2.6).  A disposable con (+5 more)

### Community 18 - "OPSX Commands"
Cohesion: 0.36
Nodes (9): OpenSpec, OPSX Apply, OPSX Archive, OPSX Bulk Archive, OPSX Explore, OPSX Fast Forward, OPSX New, OPSX Propose (+1 more)

### Community 19 - "Request Identity Scope"
Cohesion: 0.14
Nodes (23): APIRouter, CheckStatus, create_health_router(), LivenessResponse, BaseModel, FastAPI application factory.  FastAPI hosts operational endpoints (liveness/read, Liveness never touches dependencies., One readiness probe result, free of sensitive details. (+15 more)

### Community 20 - "Release Process"
Cohesion: 0.33
Nodes (7): Release Baseline (last tag), English Release Notes, gh release create (tag + publish), Release Process Skill, Stale Local Tags, Version Drift, recallum

### Community 38 - "Exception Base Type"
Cohesion: 0.25
Nodes (8): Pydantic Reference, No Ellipsis Convention, No RootModel Convention, TypeAdapter, No Ellipsis Convention, No RootModel Convention, Pydantic Models, Memory validation and retrieval limits value object.

### Community 39 - "SessionContextBudget"
Cohesion: 0.29
Nodes (7): AuthSettings, DatabaseSettings, OllamaSettings, BaseModel, PostgreSQL connection settings., Local Ollama embedding service settings., API key authentication settings.

### Community 40 - "Container"
Cohesion: 0.43
Nodes (6): _docker_available(), _free_port(), pg_database(), Shared fixtures for integration tests: a disposable PostgreSQL+pgvector.  Starts, Start PostgreSQL+pgvector with the production owner/RLS role shape., _run_migrations()

### Community 42 - "recallum_hook.py"
Cohesion: 0.36
Nodes (9): _emit(), _git(), main(), _project(), Path, Name a Recallum tool the way the running client exposes it.      Claude Code exp, _read_payload(), _remote_key() (+1 more)

### Community 43 - "marketplace.json"
Cohesion: 0.29
Nodes (6): description, name, owner, name, plugins, $schema

### Community 44 - "install.sh"
Cohesion: 0.52
Nodes (5): install_for_claude(), install_for_codex(), run_action(), install.sh script, usage()

### Community 45 - "Recallum Setup"
Cohesion: 0.29
Nodes (6): Cross-session Check, Diagnostics, Recallum Setup, Setup — Claude Code, Setup — Codex, Shared Checks

### Community 46 - "AuthSettings"
Cohesion: 0.14
Nodes (13): After installing, Development, How the API key is handled, Install, Options, Prerequisites, Recallum Memory plugin, Reconfiguring (+5 more)

### Community 47 - "Q: Okay ¿cuáles son las variables de entorno que hay que colocar?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Okay ¿cuáles son las variables de entorno que hay que colocar?, Source Nodes

### Community 48 - "Q: ¿Así está bien? Configuración Dockerfile en Dokploy"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: ¿Así está bien? Configuración Dockerfile en Dokploy, Source Nodes

### Community 49 - "Q: Dokploy build error: /recallum not found"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Dokploy build error: /recallum not found, Source Nodes

### Community 50 - "Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: ¿Cómo saber si Recallum reconoce la base de datos y cómo aplicar migraciones en Dokploy?, Source Nodes

### Community 51 - "Recallum Memory"
Cohesion: 0.33
Nodes (5): Completion Criteria, Recallum Memory, Safety, Tool Names, Workflow

### Community 53 - "conftest.py"
Cohesion: 0.12
Nodes (12): EmbeddingError, Exception, Raised when Ollama cannot produce an embedding for a text., FakeEmbeddingClient, Deterministic hash-seeded vectors; availability is configurable., _exploding_server(), _ExplodingMemoryService, Exception (+4 more)

### Community 56 - "OllamaEmbeddingClient"
Cohesion: 0.13
Nodes (16): AsyncClient, OllamaEmbeddingClient, Calls the local Ollama ``/api/embed`` endpoint synchronously per text.      Memo, Return the embedding vector for ``text`` or raise ``EmbeddingError``., Cheap readiness probe against Ollama's version endpoint., MemoryLimits, BaseModel, Memory validation and retrieval limits. (+8 more)

### Community 57 - "errors.py"
Cohesion: 0.29
Nodes (5): F, Ollama embedding client with bounded timeouts and bounded errors., One translation point from domain errors to ``ToolError``.  Applied as a decorat, Translate memory-domain errors raised by a tool into ``ToolError``., translates_domain_errors()

## Knowledge Gaps
- **72 isolated node(s):** `$schema`, `name`, `description`, `name`, `plugins` (+67 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `docker-compose.yml (local stack)` (2× useful, score=1.99974775)
- `recallum service` (2× useful, score=1.99974775)
- `Operations runbook` (2× useful, score=1.99974775)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pydantic Reference` connect `Exception Base Type` to `Database Models and Schemas`, `Request Identity Scope`, `FastAPI Skill Reference`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `Container` connect `Request Identity Scope` to `Settings and DI Container`, `Database Models and Schemas`, `Memory Service Interface`, `Auth Middleware Tests`, `MCP Tool Tests`, `In-Memory Test Adapters`, `Memory Service Tests`, `Admin CLI Tests`, `Database Integration Tests`, `conftest.py`, `OllamaEmbeddingClient`?**
  _High betweenness centrality (0.053) - this node is a cross-community bridge._
- **Why does `MemoryVisibility` connect `Repository Contract Suite` to `In-Memory Test Adapters`, `Database Models and Schemas`, `Identity and API Keys`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `MemoryService` (e.g. with `Container` and `Memory`) actually correct?**
  _`MemoryService` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Memory` (e.g. with `Base` and `MemoryRepository`) actually correct?**
  _`Memory` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `FakeEmbeddingClient` (e.g. with `Settings` and `Container`) actually correct?**
  _`FakeEmbeddingClient` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `Settings` (e.g. with `CheckStatus` and `LivenessResponse`) actually correct?**
  _`Settings` has 14 INFERRED edges - model-reasoned connections that need verification._