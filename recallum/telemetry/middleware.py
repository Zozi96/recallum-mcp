"""FastMCP middleware that observes only content-free operation metadata."""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from recallum.auth.identity import require_identity
from recallum.diagnostics import EMBEDDING_UNAVAILABLE_MESSAGE
from recallum.telemetry.buffer import TelemetryBuffer
from recallum.telemetry.events import ToolActivityEvent
from recallum.telemetry.metrics import WRITE_TOOLS

logger = logging.getLogger("recallum.telemetry")
MAX_RECORDED_PROJECT_CHARS = 200


def _result_metrics(result: Any) -> tuple[int, bool, bool]:
    structured = getattr(result, "structured_content", None) or {}
    failed = bool(getattr(result, "is_error", False))
    degraded = structured.get("mode") == "degraded_textual"
    for key in ("results", "items"):
        value = structured.get(key)
        if isinstance(value, list):
            return len(value), degraded, failed
    for key in ("total_items", "total"):
        value = structured.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value), degraded, failed
    if isinstance(structured.get("memory"), dict):
        return 1, degraded, failed
    for key in ("updated", "forgotten"):
        value = structured.get(key)
        if isinstance(value, bool):
            return int(value), degraded, failed
    return 0, degraded, failed


def _is_embedding_unavailable_error(tool_name: str, exc: BaseException) -> bool:
    return (
        tool_name in WRITE_TOOLS
        and isinstance(exc, ToolError)
        and str(exc) == EMBEDDING_UNAVAILABLE_MESSAGE
    )


def _embedding_unavailable_write(tool_name: str, result: Any) -> bool:
    if tool_name not in WRITE_TOOLS:
        return False
    structured = getattr(result, "structured_content", None) or {}
    if structured.get("embedding_degraded") is True:
        return True
    if structured.get("error") == EMBEDDING_UNAVAILABLE_MESSAGE:
        return True
    for key in ("results", "items"):
        value = structured.get(key)
        if isinstance(value, list) and any(
            isinstance(item, dict)
            and (
                item.get("error") == EMBEDDING_UNAVAILABLE_MESSAGE
                or item.get("embedding_degraded") is True
            )
            for item in value
        ):
            return True
    return False


def _safe_project(value: object) -> str | None:
    """Keep only bounded, normalized project metadata."""
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()
    if not normalized or len(normalized) > MAX_RECORDED_PROJECT_CHARS:
        return None
    return normalized


class UsageTelemetryMiddleware(Middleware):
    """Time authenticated calls and enqueue metadata without repository access."""

    def __init__(
        self,
        buffer: TelemetryBuffer,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self._buffer = buffer
        self._clock_ns = clock_ns

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        started = self._clock_ns()
        message = context.message
        tool_name = message.name
        arguments = message.arguments
        project_value = arguments.get("project") if isinstance(arguments, dict) else None
        try:
            result = await call_next(context)
        except Exception as exc:
            await self._emit(
                started,
                tool_name,
                _safe_project(project_value),
                0,
                False,
                True,
                _is_embedding_unavailable_error(tool_name, exc),
            )
            raise
        result_count, degraded, failed = _result_metrics(result)
        project = _safe_project(project_value)
        await self._emit(
            started,
            tool_name,
            project,
            result_count,
            degraded,
            failed,
            _embedding_unavailable_write(tool_name, result),
        )
        return result

    async def _emit(
        self,
        started: int,
        tool_name: str,
        project: str | None,
        result_count: int,
        degraded: bool,
        failed: bool,
        embedding_unavailable: bool = False,
    ) -> None:
        try:
            elapsed = max(0, self._clock_ns() - started)
            await self._buffer.record(
                ToolActivityEvent(
                    user_id=require_identity().user_id,
                    tool_name=tool_name,
                    project=project,
                    duration_ms=(elapsed + 999_999) // 1_000_000,
                    result_count=result_count,
                    degraded=degraded,
                    failed=failed,
                    embedding_unavailable=embedding_unavailable,
                )
            )
        except Exception:
            # Telemetry is observational and must never alter tool behaviour.
            logger.warning("could not enqueue tool activity", exc_info=True)
