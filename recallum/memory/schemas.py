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
    """A stored memory as returned to agents.

    ``reconfirmed_at`` is the last time identical content was re-stored: a
    freshness signal that the claim still held then. ``last_recalled_at`` and
    ``recall_count`` say when and how often this memory matched a ``recall``
    query; ``context_count`` says how often it rode along in a ``context``
    snapshot, which tracks importance more than relevance. Counters are as of
    before the response carrying them was produced. NULL / 0 mean "no signal
    yet".
    """

    id: uuid.UUID
    scope: Literal["global", "project"]
    project: str | None = None
    category: Literal["preference", "decision", "constraint", "fact"]
    content: str
    importance: int
    source_client: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    reconfirmed_at: datetime | None = None
    last_recalled_at: datetime | None = None
    recall_count: int = 0
    context_count: int = 0


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
    reconfirmed_at: datetime | None = None


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


class RememberBatchItem(BaseModel):
    """One memory to store inside a ``remember_batch`` call."""

    content: str
    category: Literal["preference", "decision", "constraint", "fact"]
    project: str | None = None
    importance: int = 5
    metadata: dict[str, Any] | None = None


class RememberBatchItemOutcome(BaseModel):
    """Per-item outcome of ``remember_batch``; items succeed or fail alone.

    Exactly one of ``memory`` or ``error`` is set. ``created`` and ``similar``
    mean the same as in ``RememberResult``.
    """

    created: bool = False
    memory: MemoryOut | None = None
    similar: list[SimilarMemory] = Field(default_factory=list)
    error: str | None = None


class RememberBatchResult(BaseModel):
    """Outcome of ``remember_batch``: one entry per input item, same order."""

    results: list[RememberBatchItemOutcome]
    stored: int
    deduplicated: int
    failed: int


class ReassignResult(BaseModel):
    """Outcome of a project-key migration.

    ``conflicts`` are memories whose content already exists active under the
    target key: they stayed in place, and resolving the duplication is the
    owner's decision.
    """

    from_project: str
    to_project: str
    moved: int
    conflicts: list[uuid.UUID]


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


class MergeResult(BaseModel):
    """Outcome of ``merge_memories``.

    ``merged`` is False when any source id is unknown, foreign or already
    retired -- indistinguishable on purpose -- and nothing was changed.
    ``superseded_ids`` lists every retired source; each is linked to the new
    memory, so ``get_memory`` with history recovers exactly what was folded
    in. ``similar`` keeps the consolidation loop going: same-subject
    memories that still remain after this merge.
    """

    merged: bool
    memory: MemoryOut | None = None
    superseded_ids: list[uuid.UUID] = Field(default_factory=list)
    similar: list[SimilarMemory] = Field(default_factory=list)


class RecalledMemory(MemoryOut):
    """A memory plus its fused relevance score."""

    score: float


class RecallResult(BaseModel):
    """Outcome of ``recall`` with the retrieval mode used."""

    query: str
    mode: RecallMode
    results: list[RecalledMemory]


class ContextItem(BaseModel):
    """A compact memory entry inside a context group.

    ``content_truncated`` marks an entry clipped to fit the character budget;
    the full content is retrievable by id via ``get_memory``. ``stale`` marks
    an entry whose last confirmation (``reconfirmed_at``, else ``created_at``)
    is older than the server's staleness threshold: verify it against reality
    before trusting it, then re-store it unchanged to reconfirm, update it,
    or forget it.
    """

    id: uuid.UUID
    category: Literal["preference", "decision", "constraint", "fact"]
    content: str
    scope: Literal["global", "project"]
    project: str | None = None
    importance: int
    created_at: datetime
    reconfirmed_at: datetime | None = None
    content_truncated: bool = False
    stale: bool = False


class ContextGroup(BaseModel):
    """Memories grouped by category for session context."""

    category: Literal["preference", "decision", "constraint", "fact"]
    items: list[ContextItem]


class ContextResult(BaseModel):
    """Compact session context within the requested budget.

    ``total_available`` counts every active memory visible to the request;
    ``omitted`` is how many of those the budget left out. When ``omitted`` is
    positive, ``recall`` with a focused query is the way to reach the rest.
    ``focus`` echoes the task focus that biased the snapshot, when one was
    given.
    """

    project: str | None = None
    focus: str | None = None
    groups: list[ContextGroup]
    total_items: int
    total_available: int
    omitted: int
    truncated: bool


class ListResult(BaseModel):
    """A page of memories with total count."""

    items: list[MemoryOut]
    total: int
    limit: int
    offset: int


class GetResult(BaseModel):
    """Outcome of ``get_memory``; unknown, foreign and retired ids look identical.

    ``history`` is present only when requested: the retired memories this one
    superseded, oldest first, each carrying the content that was corrected
    away. ``None`` means history was not asked for; ``[]`` means the memory
    never replaced anything.
    """

    found: bool
    memory: MemoryOut | None = None
    history: list[MemoryOut] | None = None


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
