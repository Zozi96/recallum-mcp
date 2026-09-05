"""The deliberately small event accepted by the telemetry boundary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ToolActivityEvent:
    user_id: uuid.UUID
    tool_name: str
    project: str | None
    duration_ms: int
    result_count: int
    degraded: bool
    failed: bool
    embedding_unavailable: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: uuid.UUID = field(default_factory=uuid.uuid4)
