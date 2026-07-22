"""Public schemas returned by the memory tools.

These shapes are what MCP clients see. They deliberately never expose
``user_id``: identity always comes from the authenticated key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RecallMode = Literal["hybrid", "degraded_textual"]


class MemoryOut(BaseModel):
    """A stored memory as returned to agents."""

    id: uuid.UUID
    scope: Literal["global", "project"]
    project: str | None = None
    category: Literal["preference", "decision", "constraint", "fact"]
    content: str
    importance: int
    source_client: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RememberResult(BaseModel):
    """Outcome of ``remember``; ``created`` is False for deduplicated stores."""

    memory: MemoryOut
    created: bool


class RecalledMemory(MemoryOut):
    """A memory plus its fused relevance score."""

    score: float


class RecallResult(BaseModel):
    """Outcome of ``recall`` with the retrieval mode used."""

    query: str
    mode: RecallMode
    results: list[RecalledMemory]


class ContextItem(BaseModel):
    """A compact memory entry inside a context group."""

    id: uuid.UUID
    category: Literal["preference", "decision", "constraint", "fact"]
    content: str
    scope: Literal["global", "project"]
    project: str | None = None
    importance: int
    created_at: datetime


class ContextGroup(BaseModel):
    """Memories grouped by category for session context."""

    category: Literal["preference", "decision", "constraint", "fact"]
    items: list[ContextItem]


class ContextResult(BaseModel):
    """Compact session context within the requested budget."""

    project: str | None = None
    groups: list[ContextGroup]
    total_items: int
    truncated: bool


class ListResult(BaseModel):
    """A page of memories with total count."""

    items: list[MemoryOut]
    total: int
    limit: int
    offset: int


class ForgetResult(BaseModel):
    """Outcome of ``forget``; missing and foreign ids look identical."""

    id: uuid.UUID
    forgotten: bool
