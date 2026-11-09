"""Opt-in Sentry-compatible error reporting without content telemetry."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event

from recallum import __version__

if TYPE_CHECKING:
    from recallum.config import Settings

logger = logging.getLogger("recallum.errors")
_REDACTED = "[redacted]"
_CONTENT_FIELDS = (
    "breadcrumbs",
    "contexts",
    "extra",
    "logentry",
    "message",
    "request",
    "server_name",
    "spans",
    "transaction",
    "transaction_info",
    "user",
)
_FRAME_CONTENT_FIELDS = ("context_line", "post_context", "pre_context", "vars")
_SAFE_TAGS = {"correlation_id", "surface"}
_DATA_COLLECTION: dict[str, Any] = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_headers": {"request": {"mode": "off"}},
    "http_bodies": [],
    "url_query_params": {"mode": "off"},
    "graphql": {"document": False, "variables": False},
    "gen_ai": {"inputs": False, "outputs": False},
    "database_query_data": False,
    "queues": False,
    "stack_frame_variables": False,
    "frame_context_lines": 0,
}


def _sanitize_stacktrace(stacktrace: Any) -> None:
    if not isinstance(stacktrace, dict):
        return
    frames = stacktrace.get("frames")
    if not isinstance(frames, list):
        return
    for frame in frames:
        if isinstance(frame, dict):
            for field in _FRAME_CONTENT_FIELDS:
                frame.pop(field, None)


def _sanitize_event(event: Event, hint: dict[str, Any]) -> Event:
    """Keep diagnostic structure while removing user-authored content."""
    mutable_event = cast(dict[str, Any], event)
    for field in _CONTENT_FIELDS:
        mutable_event.pop(field, None)

    exception = event.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    value["value"] = _REDACTED
                    _sanitize_stacktrace(value.get("stacktrace"))

    threads = event.get("threads")
    if isinstance(threads, dict):
        values = threads.get("values")
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict):
                    _sanitize_stacktrace(value.get("stacktrace"))

    tags = event.get("tags")
    if isinstance(tags, dict):
        event["tags"] = {key: value for key, value in tags.items() if key in _SAFE_TAGS}
    return event


def before_send_transaction(event: dict[str, Any], hint: dict[str, Any]) -> None:
    """Drop transactions: an incoming sampled sentry-trace header can force one."""
    return None


def configure_error_reporting(settings: Settings) -> None:
    """Initialize error-only reporting when an operator supplies a DSN."""
    dsn = settings.error_reporting.dsn.get_secret_value()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.environment,
        release=f"recallum@{__version__}",
        integrations=[
            StarletteIntegration(failed_request_status_codes=set()),
            FastApiIntegration(failed_request_status_codes=set()),
        ],
        default_integrations=False,
        auto_enabling_integrations=False,
        data_collection=_DATA_COLLECTION,
        include_local_variables=False,
        include_source_context=False,
        max_breadcrumbs=0,
        auto_session_tracking=False,
        before_send=_sanitize_event,
        before_send_transaction=before_send_transaction,
    )


def capture_unexpected_error(error: Exception, *, correlation_id: str) -> None:
    """Capture an unexpected MCP failure without changing tool behavior."""
    try:
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("surface", "mcp")
            scope.set_tag("correlation_id", correlation_id)
            sentry_sdk.capture_exception(error)
    except Exception:
        # Error reporting is observational; never replace the original failure.
        logger.warning("could not report MCP operation failure")


__all__ = ["capture_unexpected_error", "configure_error_reporting"]
