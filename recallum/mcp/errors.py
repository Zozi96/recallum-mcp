"""One translation point from tool failures to safe ``ToolError`` messages.

Applied as a decorator rather than as FastMCP middleware: ``call_tool``
catches every exception a tool body raises and converts it to ``ToolError``
before the middleware chain regains control, so an ``on_call_tool`` middleware
can never observe a domain error. The decorator runs inside the tool body,
where the error is still itself. Infrastructure failures are diagnosed with
sanitized class/frame metadata; exception arguments never cross the boundary.
"""

from __future__ import annotations

import functools
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp.exceptions import ToolError

from recallum.diagnostics import (
    EMBEDDING_UNAVAILABLE_MESSAGE,
    diagnostic_correlation,
    record_sanitized_failure,
)
from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError
from recallum.skills import SkillValidationError

logger = logging.getLogger("recallum.mcp")

GENERIC_TOOL_ERROR_MESSAGE = "internal server error"


def translates_domain_errors[F: Callable[..., Awaitable[Any]]](tool: F) -> F:
    """Translate tool failures into safe ``ToolError`` messages."""

    @functools.wraps(tool)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        public_message: str
        correlation_id = f"mcp-{uuid.uuid4().hex}"
        with diagnostic_correlation(correlation_id):
            try:
                return await tool(*args, **kwargs)
            except (MemoryValidationError, SkillValidationError) as exc:
                public_message = str(exc)
            except EmbeddingError as exc:
                record_sanitized_failure(logger, exc, message="MCP operation failure")
                public_message = EMBEDDING_UNAVAILABLE_MESSAGE
            except Exception as exc:
                record_sanitized_failure(logger, exc, message="MCP operation failure")
                public_message = f"{GENERIC_TOOL_ERROR_MESSAGE} (reference: {correlation_id})"

        # Raise only after the handled exception and its context have left scope.
        # FastMCP logs and records this public exception in OTel, so it must not
        # retain a sensitive provider exception through __cause__ or __context__.
        raise ToolError(public_message)

    return wrapper  # type: ignore[return-value]


__all__ = [
    "EMBEDDING_UNAVAILABLE_MESSAGE",
    "GENERIC_TOOL_ERROR_MESSAGE",
    "translates_domain_errors",
]
