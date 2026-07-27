"""One translation point from domain errors to ``ToolError``.

Applied as a decorator rather than as FastMCP middleware: ``call_tool``
catches every exception a tool body raises and converts it to ``ToolError``
before the middleware chain regains control, so an ``on_call_tool`` middleware
can never observe a domain error. The decorator runs inside the tool body,
where the error is still itself.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp.exceptions import ToolError

from recallum.embeddings.ollama import EmbeddingError
from recallum.memory import MemoryValidationError


def translates_domain_errors[F: Callable[..., Awaitable[Any]]](tool: F) -> F:
    """Translate memory-domain errors raised by a tool into ``ToolError``."""

    @functools.wraps(tool)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await tool(*args, **kwargs)
        except MemoryValidationError as exc:
            raise ToolError(str(exc)) from exc
        except EmbeddingError as exc:
            raise ToolError(f"could not embed memory content: {exc}") from exc

    return wrapper  # type: ignore[return-value]


__all__ = ["translates_domain_errors"]
