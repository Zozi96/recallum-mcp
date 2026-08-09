"""Privacy-safe HTTP request timing for FastAPI and mounted FastMCP traffic."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recallum.diagnostics import diagnostic_correlation

logger = logging.getLogger("recallum.http")

REQUEST_ID_HEADER = b"x-request-id"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
UUID_SEGMENT = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def normalize_route_template(path: str) -> str:
    """Replace UUID path segments so telemetry keys stay low-cardinality."""
    if not path:
        return "/"
    parts = path.split("/")
    normalized = [
        "{id}" if part and UUID_SEGMENT.fullmatch(part) else part for part in parts
    ]
    return "/".join(normalized) or "/"


def resolve_request_id(raw: str | None) -> str:
    """Accept a bounded inbound ID or replace it with a fresh UUID4 hex."""
    if raw is not None and REQUEST_ID_PATTERN.fullmatch(raw):
        return raw
    return uuid.uuid4().hex


class RequestTelemetryMiddleware:
    """Emit exactly one content-free timing record per HTTP request."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        emit: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.app = app
        self._clock_ns = clock_ns
        self._emit = emit or self._log_record

    @staticmethod
    def _log_record(record: dict[str, Any]) -> None:
        logger.info(
            "request method=%s route=%s status=%s latency_ms=%s request_id=%s",
            record["method"],
            record["route"],
            record["status"],
            record["latency_ms"],
            record["request_id"],
            extra=record,
        )

    @staticmethod
    def _header(scope: Scope, name: bytes) -> str | None:
        for key, value in scope.get("headers", []):
            if key.lower() == name:
                return value.decode("latin-1")
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = self._clock_ns()
        request_id = resolve_request_id(self._header(scope, REQUEST_ID_HEADER))
        method = scope.get("method", "GET")
        route = normalize_route_template(scope.get("path", "/"))
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != REQUEST_ID_HEADER
                ]
                headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        with diagnostic_correlation(request_id):
            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                self._emit_once(
                    started=started,
                    method=method,
                    route=route,
                    status=status_code,
                    request_id=request_id,
                )

    def _emit_once(
        self,
        *,
        started: int,
        method: str,
        route: str,
        status: int,
        request_id: str,
    ) -> None:
        elapsed_ms = max(0, (self._clock_ns() - started + 999_999) // 1_000_000)
        record = {
            "method": method,
            "route": route,
            "status": status,
            "latency_ms": elapsed_ms,
            "request_id": request_id,
        }
        try:
            self._emit(record)
        except Exception:
            logger.warning("could not emit request telemetry", exc_info=True)


__all__ = [
    "RequestTelemetryMiddleware",
    "normalize_route_template",
    "resolve_request_id",
]
