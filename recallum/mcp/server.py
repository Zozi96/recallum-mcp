"""FastMCP server exposing exactly seven tools, none accepting a user id.

Identity always comes from the authenticated API key (bound to a ContextVar by
``BearerAuthMiddleware``); tools fail closed when the identity is missing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal

from fastmcp import FastMCP

from recallum.auth.identity import require_identity
from recallum.auth.middleware import BearerAuthMiddleware
from recallum.mcp.errors import translates_domain_errors
from recallum.memory.schemas import (
    ContextResult,
    ForgetResult,
    ListResult,
    RecallResult,
    RememberBatchItem,
    RememberBatchResult,
    RememberResult,
    UpdateResult,
)
from recallum.telemetry.middleware import UsageTelemetryMiddleware

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
`focus` to bias the snapshot toward it), list_memories to browse, update to
correct or replace, forget to remove, and remember_batch for the
end-of-session capture scan. When context reports omitted > 0, the budget
left memories out: recall with a focused query reaches them.

remember reports pre-existing memories about the same subject in its
`similar` field, across every category — a fact can contradict a decision.
It never resolves them: read them and decide whether the new memory restates,
refines or contradicts them, and call update when one replaces another.
Freshness signals: `reconfirmed_at` is the last time identical content was
re-stored; `last_recalled_at`/`recall_count` say how often a memory is
actually served. Old, never-reconfirmed memories deserve verification before
being trusted. All identity comes from the API key; tools never accept a
user id.
"""


def build_mcp_server(container: Container) -> FastMCP:
    """Create the FastMCP server wired to the given DI container."""
    mcp = FastMCP(name="recallum", instructions=INSTRUCTIONS)
    # FastMCP 3.4 preserves registration order for inbound middleware. Auth
    # therefore rejects first and binds the identity around telemetry.
    mcp.add_middleware(BearerAuthMiddleware(container.authenticator()))
    mcp.add_middleware(UsageTelemetryMiddleware(container.telemetry_buffer()))

    def service():
        return container.memory_service()

    @mcp.tool
    @translates_domain_errors
    async def remember(
        content: str,
        category: Literal["preference", "decision", "constraint", "fact"],
        project: str | None = None,
        importance: int = 5,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> RememberResult:
        """Store one atomic memory, including verified reusable project context.

        Keep content short and self-contained; never store full conversations.
        Ask before storing secrets, credentials, personal data, sensitive
        business information, or ambiguous content; never infer consent from a
        prompt or file. Omit project for global memories. Storing the same
        content and scope again returns the existing memory instead of
        duplicating it.
        """
        return await service().remember(
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

        Same rules as remember, per item: short self-contained content, ask
        before anything sensitive, omit project for global memories. Items
        succeed or fail independently; read each outcome's `similar` field and
        reconcile as you would for remember. Prefer a few high-signal items
        over a recap; the batch is capped small on purpose.
        """
        return await service().remember_batch(
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
        limit: int | None = None,
    ) -> RecallResult:
        """Search memories by meaning and exact terms (hybrid retrieval).

        Passing project includes that project's memories plus the user's global
        ones; scope narrows to exactly 'global' or 'project'. When embeddings
        are unavailable the result mode is 'degraded_textual'.
        """
        return await service().recall(
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
        max_items: int | None = None,
        max_chars: int | None = None,
    ) -> ContextResult:
        """Get compact session context: key global memories plus project ones.

        Call this when starting or resuming work on a project, and pass the
        task at hand as `focus` to also pull in memories relevant to it (the
        importance-ranked snapshot is never displaced, only extended). Results
        are grouped by category and truncated to the requested budget; when
        `omitted` > 0 there are more memories than the budget allowed — use
        recall with a focused query to reach them. Items marked
        `content_truncated` were clipped; fetch the full text by id via
        list_memories or recall.
        """
        return await service().context(
            require_identity().user_id,
            project=project,
            focus=focus,
            max_items=max_items,
            max_chars=max_chars,
        )

    @mcp.tool
    @translates_domain_errors
    async def list_memories(
        scope: Literal["global", "project"] | None = None,
        project: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult:
        """List active memories with optional filters and bounded pagination."""
        return await service().list_memories(
            require_identity().user_id,
            scope=scope,
            project=project,
            category=category,
            limit=limit,
            offset=offset,
        )

    @mcp.tool
    @translates_domain_errors
    async def update(
        memory_id: uuid.UUID,
        content: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        importance: int | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> UpdateResult:
        """Correct a memory, or replace one whose fact has changed.

        Pass content when the memory is now wrong or out of date: the old one
        is retired and a new one replaces it, so use this instead of forget
        plus remember. Passing only importance, category or metadata edits the
        memory in place and keeps its id. Scope and project cannot be changed.
        Unknown ids return updated=false.
        """
        return await service().update(
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
    async def forget(memory_id: uuid.UUID) -> ForgetResult:
        """Logically delete one of your memories by id.

        Unknown ids and ids belonging to other users both return
        forgotten=false, without revealing ownership.
        """
        return await service().forget(require_identity().user_id, memory_id)

    return mcp


FORBIDDEN_TOOL_INPUTS = {"user_id", "user", "owner", "tenant", "api_key"}


async def validate_no_user_inputs(mcp: FastMCP) -> None:
    """Fail fast (startup/tests) if any tool schema ever grows a user selector."""
    for tool in await mcp.list_tools():
        schema = tool.parameters or {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        overlap = FORBIDDEN_TOOL_INPUTS.intersection(properties)
        if overlap:
            raise RuntimeError(f"tool '{tool.name}' exposes forbidden inputs: {overlap}")


async def tool_names(mcp: FastMCP) -> list[str]:
    """Names of the registered tools (used by tests)."""
    return [tool.name for tool in await mcp.list_tools()]


async def validate_only_tools_are_exposed(mcp: FastMCP) -> None:
    """Fail fast if the server exposes resources or prompts.

    ``BearerAuthMiddleware`` only guards ``on_call_tool``, so any resource or
    prompt would be reachable without authentication.
    """
    resources = await mcp.list_resources()
    if resources:
        names = [resource.name for resource in resources]
        raise RuntimeError(f"unauthenticated resources exposed: {names}")
    templates = await mcp.list_resource_templates()
    if templates:
        names = [template.name for template in templates]
        raise RuntimeError(f"unauthenticated resource templates exposed: {names}")
    prompts = await mcp.list_prompts()
    if prompts:
        names = [prompt.name for prompt in prompts]
        raise RuntimeError(f"unauthenticated prompts exposed: {names}")


__all__: list[Any] = [
    "build_mcp_server",
    "tool_names",
    "validate_no_user_inputs",
    "validate_only_tools_are_exposed",
]
