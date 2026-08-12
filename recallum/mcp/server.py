"""FastMCP server exposing eleven tools and a read-only profile resource.

Identity always comes from the authenticated API key (bound to a ContextVar by
``BearerAuthMiddleware``); tools and resources fail closed when the identity is
missing. No tool accepts a user id.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote

from fastmcp import FastMCP

from recallum.auth.identity import require_identity
from recallum.auth.middleware import BearerAuthMiddleware, RecallumTokenVerifier
from recallum.boundary_types import (
    StrictImportanceInput,
    StrictNonNegativeOffset,
    StrictPositiveLimit,
)
from recallum.mcp.errors import translates_domain_errors
from recallum.memory.schemas import (
    ContextResult,
    ForgetResult,
    GetResult,
    ListResult,
    MergeResult,
    RecallResult,
    ReconfirmResult,
    RelatedMemoriesResult,
    RememberBatchItem,
    RememberBatchResult,
    RememberResult,
    UpdateResult,
)
from recallum.telemetry.middleware import UsageTelemetryMiddleware

# Only these resource URIs may be registered (auth covers list/read).
ALLOWED_PROFILE_RESOURCE_URIS = frozenset(
    {
        "recallum://profile",
    }
)
ALLOWED_PROFILE_RESOURCE_TEMPLATES = frozenset(
    {
        "recallum://profile/{project}",
    }
)
ALLOWED_PROMPTS = frozenset({"session-start", "capture-scan", "stale-review"})

if TYPE_CHECKING:
    from recallum.container import Container

INSTRUCTIONS = """\
Recallum stores atomic, durable context for this user only. Memories are not
limited to decisions: use facts for verified architecture, terminology,
workflows, commands, integration contracts, root causes, and recurring
gotchas. After substantial work, save only context likely to remain true and
save a future agent rediscovery — never full conversations, logs, or guesses.
Ask before storing secrets, credentials, personal data, sensitive business
information, or ambiguous content; never infer consent from a prompt or file.
Use recall to search, context to bootstrap a session (pass the task as
`focus` to bias the snapshot toward it; the response always includes a
`profile` always-on block that focus cannot evict), get_memory to fetch one
memory by id (full text and, on request, what it replaced), list_memories to
browse, related_memories to optionally explore a seed's thematic neighborhood,
reconfirm to stamp a still-true memory as fresh, update to correct or replace,
forget to remove, and remember_batch for the end-of-session capture scan. When
context reports omitted > 0, the
budget left memories out: recall with a focused query reaches them. The
read-only resource recallum://profile (and recallum://profile/{project})
exposes the materialized profile without a tool call.

Write every memory in English and phrase every recall query in English,
whatever language the session speaks: dedup is an exact hash of the stored
content and the full-text index is English-only, so one fact written once in
Spanish and once in English becomes two memories that no single query
retrieves. Keep identifiers, commands, paths, error strings and terms the
user defined verbatim; a preference about another language is itself stated
in English.

remember reports pre-existing memories about the same subject in its
`similar` field, across every category — a fact can contradict a decision.
It never resolves them: read them and decide whether the new memory restates,
refines or contradicts them. Call update when one replaces another, and
merge_memories when several restate one underlying claim — it retires all
sources into a single linked replacement, recoverable via get_memory
history. Contradictions are never merged.
Freshness signals: `reconfirmed_at` is the last time identical content was
re-stored; `last_recalled_at`/`recall_count` say how often a memory matched
a recall query, and `context_count` how often it rode along in a session
snapshot. Context items carry `stale: true` once a memory has gone
unconfirmed past the staleness threshold: verify those against reality
 before trusting them, then prefer reconfirm over re-storing unchanged, or
 update, forget, or merge_memories. The prompts session-start, capture-scan,
 and stale-review are shortcuts when the client supports MCP prompts.
All identity comes from the API key; tools never accept a user id.
"""


def build_mcp_server(container: Container) -> FastMCP:
    """Create the FastMCP server wired to the given DI container."""
    mcp = FastMCP(
        name="recallum",
        instructions=INSTRUCTIONS,
        auth=RecallumTokenVerifier(container.authenticator()),
        mask_error_details=True,
    )
    # FastMCP 3.4 preserves registration order for inbound middleware. Auth
    # therefore rejects first and binds the identity around telemetry.
    mcp.add_middleware(BearerAuthMiddleware())
    mcp.add_middleware(UsageTelemetryMiddleware(container.telemetry_buffer()))

    def memory_service():
        return container.memory_service()

    @mcp.tool
    @translates_domain_errors
    async def remember(
        content: str,
        category: Literal["preference", "decision", "constraint", "fact"],
        project: str | None = None,
        importance: StrictImportanceInput = 5,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> RememberResult:
        """Store one atomic memory, including verified reusable project context.

        Keep content short and self-contained, and write it in English
        whatever language the session speaks — dedup is an exact hash of the
        content, so the same fact in two languages is stored twice. Keep
        identifiers, commands, paths, error strings and user-defined terms
        verbatim. Never store full conversations. Ask before storing secrets,
        credentials, personal data, sensitive business information, or
        ambiguous content; never infer consent from a prompt or file. Omit
        project for global memories. Storing the same content and scope again
        returns the existing memory instead of duplicating it.
        """
        return await memory_service().remember(
            require_identity().user_id,
            content=content,
            category=category,
            project=project,
            importance=importance,
            metadata=metadata,
            source_client=source_client,
        )

    @mcp.tool
    @translates_domain_errors
    async def remember_batch(
        items: list[RememberBatchItem],
        source_client: str | None = None,
    ) -> RememberBatchResult:
        """Store several atomic memories in one call (end-of-session capture).

        Same rules as remember, per item: short self-contained content written
        in English, ask before anything sensitive, omit project for global
        memories. Items succeed or fail independently; read each outcome's
        `similar` field and reconcile as you would for remember. Prefer a few
        high-signal items over a recap; the batch is capped small on purpose.
        """
        return await memory_service().remember_batch(
            require_identity().user_id,
            items=items,
            source_client=source_client,
        )

    @mcp.tool
    @translates_domain_errors
    async def recall(
        query: str,
        project: str | None = None,
        scope: Literal["global", "project"] | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        limit: StrictPositiveLimit | None = None,
    ) -> RecallResult:
        """Search memories by meaning, exact terms and close spellings.

        Phrase the query in English, whatever language the user asked in:
        memories are stored in English and the full-text leg uses the English
        configuration, so an untranslated query loses both lexical legs.

        Hybrid retrieval: semantic similarity, full-text ranking and a
        typo-tolerant trigram leg, fused. Passing project includes that
        project's memories plus the user's global ones; scope narrows to
        exactly 'global' or 'project'. When embeddings are unavailable the
        result mode is 'degraded_textual' (lexical legs only).
        """
        return await memory_service().recall(
            require_identity().user_id,
            query=query,
            project=project,
            scope=scope,
            category=category,
            limit=limit,
        )

    @mcp.tool
    @translates_domain_errors
    async def context(
        project: str | None = None,
        focus: str | None = None,
        max_items: StrictPositiveLimit | None = None,
        max_chars: StrictPositiveLimit | None = None,
    ) -> ContextResult:
        """Get compact session context: always-on profile plus project snapshot.

        Call this when starting or resuming work on a project. The response
        includes a `profile` block (static/dynamic always-on memories) that
        focus and importance ranking cannot evict, then category groups for
        the remaining budget. Pass `focus` to also pull task-relevant
        memories into those groups. When `omitted` > 0, use recall for the
        rest. Items marked `content_truncated` were clipped; fetch the full
        text with get_memory. Profile-only reads can use the
        recallum://profile resource instead.
        """
        return await memory_service().context(
            require_identity().user_id,
            project=project,
            focus=focus,
            max_items=max_items,
            max_chars=max_chars,
        )

    @mcp.resource(
        "recallum://profile",
        name="memory_profile",
        description="Materialized always-on memory profile for the authenticated user (global).",
        mime_type="application/json",
    )
    @translates_domain_errors
    async def memory_profile_global() -> str:
        block = await memory_service().get_profile(require_identity().user_id, project=None)
        return block.model_dump_json()

    @mcp.resource(
        "recallum://profile/{project}",
        name="memory_profile_project",
        description="Materialized memory profile for one project key (owner only).",
        mime_type="application/json",
    )
    @translates_domain_errors
    async def memory_profile_project(project: str) -> str:
        block = await memory_service().get_profile(
            require_identity().user_id, project=unquote(project)
        )
        return block.model_dump_json()

    @mcp.tool
    @translates_domain_errors
    async def get_memory(
        memory_id: uuid.UUID,
        include_history: bool = False,
    ) -> GetResult:
        """Fetch one active memory by id, with its full untruncated content.

        Use it to read items context marked `content_truncated`, or to
        re-verify a memory before trusting it. With include_history=true the
        result also lists the retired memories this one replaced, oldest
        first. Unknown ids, other users' ids and retired ids all return
        found=false.
        """
        return await memory_service().get(
            require_identity().user_id,
            memory_id,
            include_history=include_history,
        )

    @mcp.tool
    @translates_domain_errors
    async def related_memories(
        memory_id: uuid.UUID,
        limit: StrictPositiveLimit | None = None,
    ) -> RelatedMemoriesResult:
        """List bounded thematic neighbours of one active memory.

        The response contains no embeddings or full graph. Unknown, foreign,
        and retired ids return an empty related list.
        """
        return await memory_service().related_memories(
            require_identity().user_id,
            memory_id,
            limit=limit,
        )

    @mcp.tool
    @translates_domain_errors
    async def reconfirm(memory_id: uuid.UUID) -> ReconfirmResult:
        """Stamp an active memory as freshly verified without rewriting it.

        Unknown, foreign, and retired ids return reconfirmed=false.
        """
        return await memory_service().reconfirm(require_identity().user_id, memory_id)

    @mcp.tool
    @translates_domain_errors
    async def list_memories(
        scope: Literal["global", "project"] | None = None,
        project: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        stale: bool | None = None,
        limit: StrictPositiveLimit | None = None,
        offset: StrictNonNegativeOffset = 0,
    ) -> ListResult:
        """List active memories with optional filters and bounded pagination.

        stale=true is the verification queue: only memories whose last
        confirmation (reconfirmed_at, else created_at) is older than the
        server's staleness threshold. Verify each against reality, then
        prefer reconfirm over identical re-remember, or update or forget it.
        stale=false keeps only fresh memories.
        """
        return await memory_service().list_memories(
            require_identity().user_id,
            scope=scope,
            project=project,
            category=category,
            stale=stale,
            limit=limit,
            offset=offset,
        )

    @mcp.tool
    @translates_domain_errors
    async def update(
        memory_id: uuid.UUID,
        content: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        importance: StrictImportanceInput | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> UpdateResult:
        """Correct a memory, or replace one whose fact has changed.

        Pass content — in English, like every stored memory — when the memory
        is now wrong or out of date: the old one is retired and a new one
        replaces it, so use this instead of forget plus remember. Rewriting a
        memory that is still true only to translate it is not an update.
        Passing only importance, category or metadata edits the memory in
        place and keeps its id. Scope and project cannot be changed. Unknown
        ids return updated=false.
        """
        return await memory_service().update(
            require_identity().user_id,
            memory_id,
            content=content,
            category=category,
            importance=importance,
            metadata=metadata,
            source_client=source_client,
        )

    @mcp.tool
    @translates_domain_errors
    async def merge_memories(
        source_ids: list[uuid.UUID],
        content: str,
        category: Literal["preference", "decision", "constraint", "fact"],
        importance: StrictImportanceInput | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> MergeResult:
        """Consolidate two or more overlapping memories into one statement.

        Use it when `similar` or a stale-queue review shows several memories
        making the same underlying claim: write the consolidated content in
        English and list every source id. Sources that say the same thing in
        different languages are restatements, so this is how they collapse
        into one. All sources are retired and linked to the new memory —
        recoverable via get_memory with history, never deleted.
        Sources must share one scope and project; importance defaults to the
        loudest source. Restatements and refinements only: resolving a
        contradiction is an update of the wrong memory, not a merge. If any
        source id is unknown, merged=false and nothing changed.
        """
        return await memory_service().merge(
            require_identity().user_id,
            source_ids=source_ids,
            content=content,
            category=category,
            importance=importance,
            metadata=metadata,
            source_client=source_client,
        )

    @mcp.tool
    @translates_domain_errors
    async def forget(memory_id: uuid.UUID) -> ForgetResult:
        """Logically delete one of your memories by id.

        Unknown ids and ids belonging to other users both return
        forgotten=false, without revealing ownership.
        """
        return await memory_service().forget(require_identity().user_id, memory_id)

    @mcp.prompt(name="session-start")
    def session_start(project: str | None = None, focus: str | None = None) -> str:
        """Bootstrap project context before planning."""
        task = f" and focus={focus!r}" if focus else ""
        return (
            f"Call context with project={project!r}{task}. If the task is known, "
            "include focus; then use recall for focused detail when needed."
        )

    @mcp.prompt(name="capture-scan")
    def capture_scan() -> str:
        """Capture durable context at the end of a session."""
        return (
            "Run one end-of-session capture scan. Write zero or more atomic, "
            "verified reusable items in English with remember_batch; never store "
            "secrets, recaps, logs, guesses, or transient status. Zero items is valid."
        )

    @mcp.prompt(name="stale-review")
    def stale_review() -> str:
        """Review and resolve stale memories."""
        return (
            "Call list_memories with stale=true, then get_memory each item before "
            "deciding. Prefer reconfirm for a claim that remains true; use update, "
            "forget, or merge_memories when appropriate."
        )

    return mcp


FORBIDDEN_TOOL_INPUTS = {"user_id", "user", "owner", "tenant", "api_key"}


async def validate_no_user_inputs(mcp: FastMCP) -> None:
    """Fail fast (startup/tests) if any tool schema ever grows a user selector."""
    for tool in await mcp.list_tools(run_middleware=False):
        schema = tool.parameters or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        overlap = FORBIDDEN_TOOL_INPUTS.intersection(properties)
        if overlap:
            raise RuntimeError(f"tool '{tool.name}' exposes forbidden inputs: {overlap}")


async def tool_names(mcp: FastMCP) -> list[str]:
    """Names of the registered tools (used by tests)."""
    return [tool.name for tool in await mcp.list_tools(run_middleware=False)]


async def validate_only_tools_are_exposed(mcp: FastMCP) -> None:
    """Fail fast if the server exposes unexpected resources or prompts.

    Profile resources are allowed; BearerAuthMiddleware authenticates list/read.
    Uses the local compatibility seam so startup validation does not need a
    bearer token. Only the three workflow prompts are allowlisted; an empty
    prompt registry remains valid for resource-only compatibility fixtures.
    """
    from recallum.mcp.compatibility import (
        list_local_prompts,
        list_local_resource_templates,
        list_local_resources,
    )

    resources = await list_local_resources(mcp)
    resource_uris = {str(resource.uri) for resource in resources}
    unexpected = resource_uris - ALLOWED_PROFILE_RESOURCE_URIS
    if unexpected:
        raise RuntimeError(f"unexpected resources exposed: {sorted(unexpected)}")
    templates = await list_local_resource_templates(mcp)
    template_uris = {
        str(getattr(template, "uri_template", "") or getattr(template, "uriTemplate", ""))
        for template in templates
    }
    unexpected_templates = {
        uri for uri in template_uris if uri and uri not in ALLOWED_PROFILE_RESOURCE_TEMPLATES
    }
    if unexpected_templates:
        raise RuntimeError(
            f"unexpected resource templates exposed: {sorted(unexpected_templates)}"
        )
    prompts = await list_local_prompts(mcp)
    names = [prompt.name for prompt in prompts]
    unexpected_prompts = set(names) - ALLOWED_PROMPTS
    if unexpected_prompts:
        raise RuntimeError(f"unexpected prompts exposed: {sorted(unexpected_prompts)}")


__all__: list[Any] = [
    "build_mcp_server",
    "tool_names",
    "validate_no_user_inputs",
    "validate_only_tools_are_exposed",
]
