"""In-memory operational metrics snapshot and operator-only access checks."""

from __future__ import annotations

import hmac
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, Field

WRITE_TOOLS = frozenset(
    {"remember", "remember_batch", "update", "merge_memories", "save_skill"}
)


class ToolLatencySnapshot(BaseModel):
    """Per-tool latency aggregates; ``tool_name`` is a fixed MCP tool identifier."""

    tool_name: str
    calls: int = Field(ge=0)
    duration_ms_total: int = Field(ge=0)
    duration_ms_avg: float = Field(ge=0)


class MetricsSnapshot(BaseModel):
    """Anonymous process counters. No user, query, token, or memory content."""

    dropped_events: int = Field(ge=0)
    flush_failures: int = Field(ge=0)
    pending_events: int = Field(ge=0)
    observed_calls: int = Field(ge=0)
    degraded_calls: int = Field(ge=0)
    degraded_ratio: float = Field(ge=0, le=1)
    write_calls: int = Field(ge=0)
    embedding_unavailable_writes: int = Field(ge=0)
    embedding_unavailable_write_ratio: float = Field(ge=0, le=1)
    tools: list[ToolLatencySnapshot] = Field(default_factory=list)
    readiness: dict[str, Literal["ok", "unavailable"]]


def presented_metrics_token(
    authorization: str | None, metrics_header: str | None
) -> str | None:
    """Return the operator token a client presented, if any."""
    if metrics_header:
        return metrics_header
    if authorization is None:
        return None
    scheme, _, remainder = authorization.partition(" ")
    if scheme.lower() != "bearer" or not remainder:
        return None
    return remainder


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def metrics_access_allowed(
    *,
    expected_token: str,
    presented_token: str | None,
    client_host: str | None,
) -> bool:
    """Allow loopback when no operator token is configured; never trust agent tokens."""
    if expected_token:
        if presented_token is None:
            return False
        left = presented_token.encode("utf-8")
        right = expected_token.encode("utf-8")
        if len(left) != len(right):
            hmac.compare_digest(right, right)
            return False
        return hmac.compare_digest(left, right)
    if presented_token is not None:
        return False
    return is_loopback_host(client_host)
