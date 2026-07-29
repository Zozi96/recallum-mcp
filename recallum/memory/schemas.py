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


class SimilarMemory(BaseModel):
    """An existing memory close enough to a new one to be about the same thing.

    ``similarity`` is cosine similarity between embeddings, so it measures
    overlap of subject, not agreement. Two memories can be near-identical and
    say opposite things. Deciding whether this is a restatement, a refinement
    or a contradiction requires reading both, which is the agent's job.
    """

    id: uuid.UUID
    content: str
    category: Literal["preference", "decision", "constraint", "fact"]
    importance: int
    similarity: float
    created_at: datetime


class RememberResult(BaseModel):
    """Outcome of ``remember``; ``created`` is False for deduplicated stores.

    ``similar`` lists pre-existing memories about the same subject. They are
    surfaced here, at the moment the potential conflict is created, because
    this is the only point where they are otherwise invisible: the caller sees
    its own new memory and nothing else. Nothing is resolved automatically --
    superseding one memory with another is always an explicit ``update``.
    """

    memory: MemoryOut
    created: bool
    similar: list[SimilarMemory] = Field(default_factory=list)


class UpdateResult(BaseModel):
    """Outcome of ``update``.

    ``superseded_id`` is set only when the content changed: that retires the
    old memory and returns a new one with a new id. Editing only importance,
    category or metadata keeps the same id and leaves ``superseded_id`` unset.
    ``updated`` is False for unknown and foreign ids alike.
    """

    updated: bool
    memory: MemoryOut | None = None
    superseded_id: uuid.UUID | None = None


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


class MemoryGraphNode(BaseModel):
    """One active memory in a graph snapshot."""

    id: uuid.UUID
    scope: Literal["global", "project"]
    project: str | None = None
    category: Literal["preference", "decision", "constraint", "fact"]
    content: str
    importance: int
    created_at: datetime


class MemoryGraphEdge(BaseModel):
    """One canonical undirected semantic relation."""

    source_id: uuid.UUID
    target_id: uuid.UUID
    similarity: float


class MemoryGraphResponse(BaseModel):
    """A bounded graph projection that never contains stored embeddings."""

    nodes: list[MemoryGraphNode]
    edges: list[MemoryGraphEdge]
    total: int
    truncated: bool
    model_mismatch: bool


class ForgetResult(BaseModel):
    """Outcome of ``forget``; missing and foreign ids look identical."""

    id: uuid.UUID
    forgotten: bool
