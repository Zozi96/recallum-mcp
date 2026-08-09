"""Single seam for private FastMCP registry inspection used at startup.

Only this module may call ``_list_resources``, ``_list_resource_templates``,
and ``_list_prompts``. Missing or incompatible private APIs fail diagnostically
so upgrades cannot silently skip exposure validation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastmcp import FastMCP


def _compatibility_error(method: str, exc: BaseException) -> RuntimeError:
    error = RuntimeError(
        "FastMCP compatibility failure: private API "
        f"{method!r} is missing or unusable. "
        "Recallum requires fastmcp>=3.4,<4; update the lock only after the "
        "compatibility contract passes."
    )
    error.__cause__ = exc
    return error


async def _call_private(mcp: FastMCP, method: str) -> Any:
    operation = getattr(mcp, method, None)
    if not callable(operation):
        raise _compatibility_error(method, AttributeError(method))
    try:
        return await operation()
    except Exception as exc:  # noqa: BLE001 — surface as startup diagnostic
        raise _compatibility_error(method, exc) from exc


async def list_local_resources(mcp: FastMCP) -> Sequence[Any]:
    """Return resources from the local FastMCP registry without auth middleware."""
    return await _call_private(mcp, "_list_resources")


async def list_local_resource_templates(mcp: FastMCP) -> Sequence[Any]:
    """Return resource templates from the local FastMCP registry."""
    return await _call_private(mcp, "_list_resource_templates")


async def list_local_prompts(mcp: FastMCP) -> Sequence[Any]:
    """Return prompts from the local FastMCP registry."""
    return await _call_private(mcp, "_list_prompts")


__all__ = [
    "list_local_prompts",
    "list_local_resource_templates",
    "list_local_resources",
]
