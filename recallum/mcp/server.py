"""FastMCP server exposing fifteen tools and a read-only profile resource.

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
    Anchor,
    ContextResult,
    ForgetResult,
    GetResult,
    Kind,
    ListResult,
    MergeResult,
    RecallResult,
    ReconfirmResult,
    RelatedMemoriesResult,
    RememberBatchItem,
    RememberBatchResult,
    RememberResult,
    SourceType,
    UpdateResult,
)
from recallum.skills.schemas import (
    ForgetSkillResult,
    GetSkillResult,
    MatchSkillsResult,
    SaveSkillResult,
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

Cycle: remember / remember_batch store; recall searches; context
bootstraps (`focus`; always-on profile cannot be evicted); get_memory
fetches one id; list_memories browses; related_memories explores
neighbors; reconfirm stamps still-true; update corrects or replaces;
merge_memories consolidates restatements; forget removes. When context
reports omitted > 0, recall with a focused query. Resources:
recallum://profile and recallum://profile/{project}.

Write every memory in English and phrase every recall query in English,
whatever language the session speaks. Keep identifiers, commands, paths,
error strings and terms the user defined verbatim.

Read `similar` before resolving; contradictions are never merged. Use
prompts session-start, capture-scan, and stale-review, plus the plugin
guide, for the full capture and review cycle. Tools never accept a user
id.
"""


def _session_start_prompt(project: str | None, focus: str | None) -> str:
    """Text returned by the session-start MCP prompt (pure, unit-testable)."""
    task = f" and focus={focus!r}" if focus else ""
    return (
        f"Call context with project={project!r}{task}. If the task is known, "
        "include focus; then use recall for focused detail when needed."
    )


def _capture_scan_prompt() -> str:
    """Text returned by the capture-scan MCP prompt (pure, unit-testable).

    Reading ``similar`` on every outcome is the contract: the server reports
    same-subject memories but never resolves them, so each must be reconciled
    by the agent before the capture closes.
    """
    return (
        "Run one end-of-session capture scan. Write zero or more atomic, "
        "verified reusable items in English with remember_batch; never store "
        "secrets, recaps, logs, guesses, or transient status. Zero items is "
        "valid. Read the similar field on every remember and remember_batch "
        "outcome: it lists existing memories about the same subject, and the "
        "server never resolves them for you. Merge when a similar memory "
        "restates or refines the same claim as your new item; update or forget "
        "the similar memory when it contradicts the new claim or is incorrect "
        "-- never merge a contradiction. Decide each similar outcome explicitly "
        "before closing the capture."
    )


def _stale_review_prompt() -> str:
    """Text returned by the stale-review MCP prompt (pure, unit-testable).

    Every verified stale item must end in one of the four resolutions; having
    merely looked at an item is not a conclusion.
    """
    return (
        "Call list_memories with stale=true, then get_memory each item and "
        "verify it against reality before deciding. End every verified item "
        "with exactly one of reconfirm (still true), update (changed), forget "
        "(no longer applies), or merge_memories (restatement of an active "
        "claim). Concluding a review without one of those four actions leaves "
        "the item unresolved."
    )


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

    def skill_service():
        return container.skill_service()

    @mcp.tool
    @translates_domain_errors
    async def remember(
        content: str,
        category: Literal["preference", "decision", "constraint", "fact"],
        kind: Kind | None = None,
        project: str | None = None,
        importance: StrictImportanceInput = 5,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
        ttl_seconds: int | None = None,
        source_type: SourceType | None = None,
        source_ref: str | None = None,
        anchors: list[Anchor] | None = None,
    ) -> RememberResult:
        """Store one atomic memory, including verified reusable project context.

        Choose remember for a single item; remember_batch for a capture scan;
        update to correct an existing id; save_skill for a procedure.
        Ask before storing secrets, credentials, personal data, sensitive
        business information, or ambiguous content; never infer consent from
        a prompt or file. Write English; keep user-defined terms verbatim.
        Read `similar` and decide: restatements may update or merge_memories;
        contradictions are never auto-merged. When embeddings are unavailable
        the write still succeeds and `embedding_degraded` is true.

        Example: remember(content="Prefer conventional commits", category="preference")
        """
        return await memory_service().remember(
            require_identity().user_id,
            content=content,
            category=category,
            kind=kind,
            project=project,
            importance=importance,
            metadata=metadata,
            source_client=source_client,
            ttl_seconds=ttl_seconds,
            source_type=source_type,
            source_ref=source_ref,
            anchors=[a.model_dump() for a in anchors] if anchors else None,
        )

    @mcp.tool
    @translates_domain_errors
    async def remember_batch(
        items: list[RememberBatchItem],
        source_client: str | None = None,
    ) -> RememberBatchResult:
        """Store several atomic memories in one call (end-of-session capture).

        Choose remember_batch for a capture scan; remember for one item.         Same
        per-item rules as remember: English, Ask before storing secrets,
        never infer consent. Read each outcome's `similar`; contradictions
        are never auto-merged. Items succeed or fail independently. When
        embeddings are unavailable the item is still stored and
        `embedding_degraded` is true.

        Example: remember_batch(items=[{"content": "Prefer conventional commits",
        "category": "preference"}])
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
        kind: Kind | None = None,
        symbol: str | None = None,
        file: str | None = None,
        limit: StrictPositiveLimit | None = None,
        max_tokens: StrictPositiveLimit | None = None,
        strategy: Literal["coding", "debugging", "planning", "review", "architecture"]
        | None = None,
    ) -> RecallResult:
        """Search memories by meaning, exact terms and close spellings.

        Choose recall for memories; match_skills for procedures. Phrase the
        query in English, whatever language the user asked in. Passing
        project includes that project plus globals; scope="project" requires
        project. Optional symbol/file filters matching anchors before rank;
        an empty list is not proof of no textual mentions — omit the filter
        and keep the identifier in query. When embeddings are unavailable
        the mode is degraded_textual. limit and max_tokens are maxima: the
        result may be shorter.

        Example: recall(query="Context budget decisions", project=P, limit=3)
        """
        return await memory_service().recall(
            require_identity().user_id,
            query=query,
            project=project,
            scope=scope,
            category=category,
            kind=kind,
            symbol=symbol,
            file=file,
            limit=limit,
            max_tokens=max_tokens,
            strategy=strategy,
        )

    @mcp.tool
    @translates_domain_errors
    async def context(
        project: str | None = None,
        focus: str | None = None,
        kind: Kind | None = None,
        max_items: StrictPositiveLimit | None = None,
        max_chars: StrictPositiveLimit | None = None,
        max_tokens: StrictPositiveLimit | None = None,
        strategy: Literal["coding", "debugging", "planning", "review", "architecture"]
        | None = None,
    ) -> ContextResult:
        """Get compact session context: always-on profile plus project snapshot.

        Choose context to bootstrap a session; recall when omitted > 0;
        get_memory for items marked content_truncated. Optional max_items /
        max_tokens are maxima. Pass focus to bias categorized groups; the
        profile cannot be evicted.

        Example: context(project=P, focus="Context budget decisions")
        """
        return await memory_service().context(
            require_identity().user_id,
            project=project,
            focus=focus,
            kind=kind,
            max_items=max_items,
            max_chars=max_chars,
            max_tokens=max_tokens,
            strategy=strategy,
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

        Choose get_memory for a known UUID or a context item marked
        content_truncated; list_memories to browse. Unknown, foreign, and
        retired ids return found=false.

        Example: get_memory(memory_id=M)
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

        Choose related_memories after you have a seed id; recall to search
        by query. Unknown, foreign, and retired ids return an empty related
        list.

        Example: related_memories(memory_id=M)
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

        Choose reconfirm when the text is still true; update to
        correct/replace; merge_memories to consolidate restatements only.
        Unknown, foreign, and retired ids return reconfirmed=false.

        Example: reconfirm(memory_id=M)
        """
        return await memory_service().reconfirm(require_identity().user_id, memory_id)

    @mcp.tool
    @translates_domain_errors
    async def list_memories(
        scope: Literal["global", "project"] | None = None,
        project: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        kind: Kind | None = None,
        stale: bool | None = None,
        limit: StrictPositiveLimit | None = None,
        offset: StrictNonNegativeOffset = 0,
    ) -> ListResult:
        """List active memories with optional filters and bounded pagination.

        Choose list_memories to browse or build the stale queue; get_memory
        to read one id in full. stale=true is the verification queue.

        Example: list_memories(stale=true, limit=10)
        """
        return await memory_service().list_memories(
            require_identity().user_id,
            scope=scope,
            project=project,
            category=category,
            kind=kind,
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
        kind: Kind | None = None,
        importance: StrictImportanceInput | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
        ttl_seconds: int | None = None,
        clear_expiry: bool = False,
        source_type: SourceType | None = None,
        source_ref: str | None = None,
    ) -> UpdateResult:
        """Correct a memory, or replace one whose fact has changed.

        Choose update to rewrite or edit attributes; reconfirm to stamp
        still-true without rewriting; merge_memories to consolidate
        restatements only. Ask before storing secrets; never infer consent.
        Content changes retire the old row. Unknown ids return updated=false.

        Example: update(memory_id=M, content="Prefer Conventional Commits")
        """
        return await memory_service().update(
            require_identity().user_id,
            memory_id,
            content=content,
            category=category,
            kind=kind,
            importance=importance,
            metadata=metadata,
            source_client=source_client,
            ttl_seconds=ttl_seconds,
            clear_expiry=clear_expiry,
            source_type=source_type,
            source_ref=source_ref,
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

        Choose merge_memories for restatements of the same claim; update to
        correct the wrong one; reconfirm does not rewrite. Read `similar`;
        contradictions are never auto-merged. Ask before storing secrets;
        never infer consent.

        Example: merge_memories(source_ids=[A, B],
        content="Prefer conventional commits", category="preference")
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

        Choose forget to retire a memory; forget_skill for a procedure.
        Unknown ids and ids belonging to other users both return
        forgotten=false, without revealing ownership.

        Example: forget(memory_id=M)
        """
        return await memory_service().forget(require_identity().user_id, memory_id)

    @mcp.tool
    @translates_domain_errors
    async def save_skill(
        name: str,
        description: str,
        triggers: list[str],
        steps: list[str],
        constraints: str | None = None,
        project: str | None = None,
        scope: Literal["global", "project"] | None = None,
        replace: bool = False,
        source_type: SourceType | None = None,
        source_ref: str | None = None,
    ) -> SaveSkillResult:
        """Store a versioned procedure -- when to apply a method, not what happened.

        Choose save_skill for a repeatable procedure; remember for an outcome
        or lesson. Ask before storing secrets; never infer consent. Read
        `similar`; contradictions are never auto-merged. Saving changed steps
        is rejected unless replace=true, which supersedes the active skill.

        Example: save_skill(name="commit-style",
        description="Conventional commits", triggers=["commit message"],
        steps=["Use type(scope): summary"])
        """
        return await skill_service().save_skill(
            require_identity().user_id,
            name=name,
            description=description,
            triggers=triggers,
            steps=steps,
            constraints=constraints,
            project=project,
            scope=scope,
            replace=replace,
            source_type=source_type,
            source_ref=source_ref,
        )

    @mcp.tool
    @translates_domain_errors
    async def match_skills(
        query: str,
        project: str | None = None,
        scope: Literal["global", "project"] | None = None,
        limit: StrictPositiveLimit | None = None,
    ) -> MatchSkillsResult:
        """Find skills by procedure -- distinct from `recall`, which searches memories.

        Choose match_skills for procedures; recall for memories.
        scope="project" requires project. When embeddings are unavailable
        the mode is degraded_textual.

        Example: match_skills(query="How to write commit messages", limit=3)
        """
        return await skill_service().match_skills(
            require_identity().user_id,
            query=query,
            project=project,
            scope=scope,
            limit=limit,
        )

    @mcp.tool
    @translates_domain_errors
    async def get_skill(skill_id: uuid.UUID) -> GetSkillResult:
        """Fetch one active skill by id, with its full triggers, steps and constraints.

        Choose get_skill for a known skill UUID; match_skills to search;
        get_memory for a memory id. Unknown, foreign, and retired ids return
        found=false.

        Example: get_skill(skill_id=S)
        """
        return await skill_service().get_skill(require_identity().user_id, skill_id)

    @mcp.tool
    @translates_domain_errors
    async def forget_skill(skill_id: uuid.UUID) -> ForgetSkillResult:
        """Logically delete one of your skills by id.

        Choose forget_skill to retire a procedure; forget for a memory.
        Unknown ids and ids belonging to other users both return
        forgotten=false, without revealing ownership.

        Example: forget_skill(skill_id=S)
        """
        return await skill_service().forget_skill(require_identity().user_id, skill_id)

    @mcp.prompt(name="session-start")
    def session_start(project: str | None = None, focus: str | None = None) -> str:
        """Bootstrap project context before planning."""
        return _session_start_prompt(project, focus)

    @mcp.prompt(name="capture-scan")
    def capture_scan() -> str:
        """Capture durable context at the end of a session."""
        return _capture_scan_prompt()

    @mcp.prompt(name="stale-review")
    def stale_review() -> str:
        """Review and resolve stale memories."""
        return _stale_review_prompt()

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
        raise RuntimeError(f"unexpected resource templates exposed: {sorted(unexpected_templates)}")
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
