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

        Keep content short and self-contained, and write it in English
        whatever language the session speaks — dedup is an exact hash of the
        content, so the same fact in two languages is stored twice. Keep
        identifiers, commands, paths, error strings and user-defined terms
        verbatim. Never store full conversations. Ask before storing secrets,
        credentials, personal data, sensitive business information, or
        ambiguous content; never infer consent from a prompt or file. Omit
        project for global memories. Storing the same content and scope again
        returns the existing memory instead of duplicating it. When content
        looks like it may not be English, the response's `language_warning`
        says so — advisory only, the write still succeeds; reword and update
        it when that happens. `ttl_seconds` is for short-lived working memory
        that should silently stop being served after it expires; omit it for
        durable context. `source_type` is who asserted the claim (agent, user,
        bootstrap, or unknown); `source_ref` is a short path, commit, or file
        id — never a transcript. Both are optional. `kind` is an optional
        coding facet orthogonal to `category` (failure, solution,
        architecture, convention, todo, command); `kind='todo'` MUST also set
        `ttl_seconds` — durable todos are rejected. `anchors` optionally
        declares structured code references (`{type, identifier}`, type one
        of file/symbol/module) so `recall` can later filter by `symbol` or
        `file`; Recallum does not parse a repository or build a code graph,
        so an identifier is stored verbatim, exactly as given.
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

        Same rules as remember, per item: short self-contained content written
        in English, ask before anything sensitive, omit project for global
        memories. Items succeed or fail independently; read each outcome's
        `similar` and `language_warning` fields and reconcile as you would
        for remember. Prefer a few high-signal items over a recap; the batch
        is capped small on purpose.
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
        strategy: Literal[
            "coding", "debugging", "planning", "review", "architecture"
        ]
        | None = None,
    ) -> RecallResult:
        """Search memories by meaning, exact terms and close spellings.

        Phrase the query in English, whatever language the user asked in:
        memories are stored in English and the full-text leg uses the English
        configuration, so an untranslated query loses both lexical legs.

        Hybrid retrieval: semantic similarity, full-text ranking and a
        typo-tolerant trigram leg, fused. Passing project includes that
        project's memories plus the user's global ones; scope narrows to
        exactly 'global' or 'project'. When embeddings are unavailable the
        result mode is 'degraded_textual' (lexical legs only). ``limit`` and
        ``max_tokens`` are maxima: the result may be shorter when few
        memories meet the server's retrieval evidence floor.

        Optional ``max_tokens`` packs by a local estimate (not the client
        model tokenizer). Optional ``strategy`` reorders fused hits by
        task-type category priority without dropping matches that still fit.
        Optional `kind` narrows to that coding facet; a memory with no kind
        never matches a concrete `kind` filter. Optional `symbol`/`file`
        restrict the candidate set to memories carrying a matching code
        anchor (exact match, normalized) before results are ranked; when
        nothing matches, the result is empty even if a semantically similar
        unanchored memory exists — pair with a query-text-only call to also
        reach content that merely mentions the identifier.
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
        strategy: Literal[
            "coding", "debugging", "planning", "review", "architecture"
        ]
        | None = None,
    ) -> ContextResult:
        """Get compact session context: always-on profile plus project snapshot.

        Call this when starting or resuming work on a project. The response
        includes a `profile` block (static/dynamic always-on memories) that
        focus and importance ranking cannot evict, then category groups for
        the remaining budget. Pass `focus` to also pull task-relevant
        memories into those groups. When `omitted` > 0, use recall for the
        rest; `omitted_by_category` names which categories still have more,
        so recall with a focused query (and that category) reaches them.
        Items marked `content_truncated` were clipped; fetch the full text
        with get_memory. Profile-only reads can use the recallum://profile
        resource instead.

        Optional ``max_items`` / ``max_tokens`` are maxima: focus admission
        may yield fewer categorized items than the budget. Optional
        ``max_tokens`` / ``strategy`` apply to the categorized
        remainder only (profile stays reserved). Token counts are a local
        estimate, not the client model tokenizer. Optional `kind` narrows the
        categorized groups and any `focus` match to that coding facet; the
        always-on `profile` block is unaffected by it.
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

        Also increments ``reconfirm_count``, a cumulative explicit-utility
        signal kept separate from serve-count usage signals. Unknown,
        foreign, and retired ids return reconfirmed=false.
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

        stale=true is the verification queue: only memories whose last
        confirmation (reconfirmed_at, else created_at) is older than the
        server's staleness threshold. Verify each against reality, then
        prefer reconfirm over identical re-remember, or update or forget it.
        stale=false keeps only fresh memories. Optional `kind` narrows to
        that coding facet; a memory with no kind never matches a concrete
        `kind` filter.
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

        Pass content — in English, like every stored memory — when the memory
        is now wrong or out of date: the old one is retired and a new one
        replaces it, so use this instead of forget plus remember. Translating
        a memory that was stored in another language into English is a
        sanctioned hygiene fix, not a casual rewrite: it recovers a memory
        the full-text index otherwise cannot reach, and supersession keeps
        the original wording in history. Rewriting a memory that is still
        true and already in English, only to reword or restyle it, is not an
        update. Passing only importance, category, metadata, ttl_seconds or
        clear_expiry edits the memory in place and keeps its id; ttl_seconds
        and clear_expiry only apply then (not alongside content) and manage a
        short-lived working memory's expiry — set a fresh one, or clear it
        back to durable. Scope and project cannot be changed. Unknown ids
        return updated=false. `source_type` and `source_ref` may be set on
        the attribute path or override copied provenance on a content change.
        `kind` may be set on the attribute path or carries forward from the
        original on a content change; `kind='todo'` MUST resolve to a
        non-null expiry (this call's ttl_seconds or one the row already
        carries) — a content change never carries an expiry forward, so
        `kind='todo'` there is always rejected.
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

        A skill is distinct from a memory: use it for a repeatable procedure
        with concrete steps, never for an outcome or a one-off lesson (that is
        `remember`). `triggers` describe when the procedure applies; `steps`
        are the ordered procedure itself; `constraints` is an optional bullet
        list of invariants the procedure must respect. Omit `project` for a
        global skill. Saving the same `name` in the same scope again returns
        the existing skill unchanged when the steps are identical
        (`created=false`). When the steps differ, the call is rejected unless
        `replace=true`, which supersedes the active skill with a new version
        and links it to what it replaced. The response's `similar` field
        lists pre-existing skills about the same procedure; it is advisory
        only and never auto-merges anything. `source_type` and `source_ref`
        mean the same as on `remember`.
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

        Hybrid retrieval over each skill's description, triggers and steps:
        semantic similarity plus full-text ranking, fused. Passing project
        includes that project's skills plus the user's global ones; scope
        narrows to exactly 'global' or 'project'. When embeddings are
        unavailable the result mode is 'degraded_textual' (textual leg only).
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

        Unknown ids, other users' ids and retired ids all return found=false.
        """
        return await skill_service().get_skill(require_identity().user_id, skill_id)

    @mcp.tool
    @translates_domain_errors
    async def forget_skill(skill_id: uuid.UUID) -> ForgetSkillResult:
        """Logically delete one of your skills by id.

        Unknown ids and ids belonging to other users both return
        forgotten=false, without revealing ownership.
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
