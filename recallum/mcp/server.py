"""FastMCP server exposing exactly five tools, none accepting a user id.

Identity always comes from the authenticated API key (bound to a ContextVar by
``BearerAuthMiddleware``); tools fail closed when the identity is missing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from recallum.auth.identity import require_identity
from recallum.auth.middleware import BearerAuthMiddleware
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.memory.schemas import (
    ContextResult,
    ForgetResult,
    ListResult,
    RecallResult,
    RememberResult,
)

if TYPE_CHECKING:
    from recallum.container import Container

INSTRUCTIONS = """\
Recallum stores atomic memories (preferences, decisions, constraints, facts)
for this user only. Save short, self-contained statements — never full
conversations. Use recall to search by meaning or exact terms, context to
bootstrap a session, list_memories to browse, and forget to remove.
All identity comes from the API key; tools never accept a user id.
"""


def build_mcp_server(container: Container) -> FastMCP:
    """Create the FastMCP server wired to the given DI container."""
    mcp = FastMCP(name="recallum", instructions=INSTRUCTIONS)
    mcp.add_middleware(BearerAuthMiddleware(container.authenticator()))

    def service():
        return container.memory_service()

    @mcp.tool
    async def remember(
        content: str,
        category: Literal["preference", "decision", "constraint", "fact"],
        project: str | None = None,
        importance: int = 5,
        metadata: dict[str, str | int | float | bool | None] | None = None,
        source_client: str | None = None,
    ) -> RememberResult:
        """Store one atomic memory (a preference, decision, constraint or fact).

        Keep content short and self-contained; never store full conversations.
        Omit project for global memories. Storing the same content and scope
        again returns the existing memory instead of duplicating it.
        """
        try:
            return await service().remember(
                require_identity().user_id,
                content=content,
                category=category,
                project=project,
                importance=importance,
                metadata=metadata,
                source_client=source_client,
            )
        except MemoryValidationError as exc:
            raise ToolError(str(exc)) from exc
        except EmbeddingError as exc:
            raise ToolError(f"could not embed memory content: {exc}") from exc

    @mcp.tool
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
        try:
            return await service().recall(
                require_identity().user_id,
                query=query,
                project=project,
                scope=scope,
                category=category,
                limit=limit,
            )
        except MemoryValidationError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    async def context(
        project: str | None = None,
        max_items: int | None = None,
        max_chars: int | None = None,
    ) -> ContextResult:
        """Get compact session context: key global memories plus project ones.

        Results are grouped by category and truncated to the requested budget.
        Call this when starting or resuming work on a project.
        """
        try:
            return await service().context(
                require_identity().user_id,
                project=project,
                max_items=max_items,
                max_chars=max_chars,
            )
        except MemoryValidationError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    async def list_memories(
        scope: Literal["global", "project"] | None = None,
        project: str | None = None,
        category: Literal["preference", "decision", "constraint", "fact"] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult:
        """List active memories with optional filters and bounded pagination."""
        try:
            return await service().list_memories(
                require_identity().user_id,
                scope=scope,
                project=project,
                category=category,
                limit=limit,
                offset=offset,
            )
        except MemoryValidationError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
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


__all__: list[Any] = ["build_mcp_server", "tool_names", "validate_no_user_inputs"]
