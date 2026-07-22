"""Memory service: remember, recall, context, list and forget.

Business rules implemented here:
- ``remember`` embeds before persisting; an exact active duplicate returns the
  existing row instead of inserting a second one.
- ``recall`` fuses vector and textual candidates with Reciprocal Rank Fusion
  and degrades to textual-only (flagged) when Ollama cannot embed the query.
- ``context`` produces a compact, category-grouped budget-aware snapshot.
- ``forget`` is a logical delete; foreign and unknown ids are indistinguishable.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.exc import IntegrityError

from recallum.db.models import Memory
from recallum.db.repositories.memory_repo import MAX_CANDIDATES, MemoryRepository, ScoredMemory
from recallum.embeddings.ollama import EmbeddingError, OllamaEmbeddingClient
from recallum.memory.normalize import content_hash as compute_hash
from recallum.memory.normalize import (
    normalize_content,
    normalize_project,
    scope_for,
    validate_category,
    validate_importance,
    validate_metadata,
)
from recallum.memory.schemas import (
    ContextGroup,
    ContextItem,
    ContextResult,
    ForgetResult,
    ListResult,
    MemoryOut,
    RecalledMemory,
    RecallResult,
    RememberResult,
)

logger = logging.getLogger("recallum.memory")

# Reciprocal Rank Fusion constant; 60 is the conventional default.
RRF_K = 60

# Category presentation order for context grouping.
CONTEXT_CATEGORY_ORDER = ("preference", "constraint", "decision", "fact")


class MemoryService:
    """Coordinates validation, embeddings, retrieval and persistence."""

    def __init__(
        self,
        repository: MemoryRepository,
        embeddings: OllamaEmbeddingClient,
        max_content_chars: int = 4000,
        max_project_chars: int = 200,
        max_metadata_bytes: int = 2048,
        max_metadata_keys: int = 16,
        recall_default_limit: int = 10,
        recall_max_limit: int = 50,
        list_default_limit: int = 50,
        list_max_limit: int = 100,
        context_default_max_items: int = 20,
        context_max_items_cap: int = 50,
        context_default_max_chars: int = 6000,
        context_max_chars_cap: int = 20000,
    ) -> None:
        self._repo = repository
        self._embeddings = embeddings
        self._max_content_chars = max_content_chars
        self._max_project_chars = max_project_chars
        self._max_metadata_bytes = max_metadata_bytes
        self._max_metadata_keys = max_metadata_keys
        self._recall_default_limit = recall_default_limit
        self._recall_max_limit = recall_max_limit
        self._list_default_limit = list_default_limit
        self._list_max_limit = list_max_limit
        self._context_default_max_items = context_default_max_items
        self._context_max_items_cap = context_max_items_cap
        self._context_default_max_chars = context_default_max_chars
        self._context_max_chars_cap = context_max_chars_cap

    # ------------------------------------------------------------------
    # remember
    # ------------------------------------------------------------------

    async def remember(
        self,
        user_id: uuid.UUID,
        *,
        content: str,
        category: str,
        project: str | None = None,
        importance: int = 5,
        metadata: dict[str, Any] | None = None,
        source_client: str | None = None,
    ) -> RememberResult:
        """Store an atomic memory, deduplicating exact active repeats."""
        normalized = normalize_content(content, self._max_content_chars)
        normalized_project = normalize_project(project, self._max_project_chars)
        validated_category = validate_category(category)
        validated_importance = validate_importance(importance)
        validated_metadata = validate_metadata(
            metadata, self._max_metadata_bytes, self._max_metadata_keys
        )
        scope = scope_for(normalized_project)
        digest = compute_hash(normalized)

        existing = await self._repo.find_active_by_hash(
            user_id, scope=scope, project=normalized_project, content_hash=digest
        )
        if existing is not None:
            return RememberResult(memory=_to_memory_out(existing), created=False)

        # Embed before persisting: a memory without a vector is never stored.
        embedding = await self._embeddings.embed(normalized)

        try:
            memory = await self._repo.create_memory(
                user_id,
                scope=scope,
                project=normalized_project,
                category=validated_category,
                content=normalized,
                content_hash=digest,
                embedding=embedding,
                importance=validated_importance,
                source_client=source_client,
                metadata=validated_metadata,
            )
        except IntegrityError:
            # Concurrent insert won the race on the partial unique index.
            racing = await self._repo.find_active_by_hash(
                user_id, scope=scope, project=normalized_project, content_hash=digest
            )
            if racing is not None:
                return RememberResult(memory=_to_memory_out(racing), created=False)
            raise
        return RememberResult(memory=_to_memory_out(memory), created=True)

    # ------------------------------------------------------------------
    # recall
    # ------------------------------------------------------------------

    async def recall(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        project: str | None = None,
        scope: str | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> RecallResult:
        """Hybrid retrieval with RRF fusion; degrades to textual on embed failure."""
        normalized_query = normalize_content(query, self._max_content_chars)
        normalized_project = normalize_project(project, self._max_project_chars)
        validated_category = validate_category(category) if category else None
        effective_limit = self._clamp_limit(
            limit, self._recall_default_limit, self._recall_max_limit
        )
        candidate_limit = min(MAX_CANDIDATES, max(effective_limit * 3, 10))

        vector_candidates: list[ScoredMemory] = []
        mode = "hybrid"
        try:
            query_embedding = await self._embeddings.embed(normalized_query)
        except EmbeddingError:
            logger.warning("embedding unavailable for recall; using textual fallback")
            mode = "degraded_textual"
        else:
            vector_candidates = list(
                await self._repo.search_vector(
                    user_id,
                    query_embedding,
                    scope=scope,
                    project=normalized_project,
                    category=validated_category,
                    limit=candidate_limit,
                )
            )

        text_candidates = list(
            await self._repo.search_text(
                user_id,
                normalized_query,
                scope=scope,
                project=normalized_project,
                category=validated_category,
                limit=candidate_limit,
            )
        )

        fused = self._reciprocal_rank_fusion(vector_candidates, text_candidates)
        results = [
            RecalledMemory(**_to_memory_out(scored.memory).model_dump(), score=score)
            for scored, score in fused[:effective_limit]
        ]
        return RecallResult(query=normalized_query, mode=mode, results=results)

    def _reciprocal_rank_fusion(
        self,
        vector_candidates: list[ScoredMemory],
        text_candidates: list[ScoredMemory],
    ) -> list[tuple[ScoredMemory, float]]:
        """Merge ranked candidate lists with RRF (k=60)."""
        scores: dict[uuid.UUID, float] = defaultdict(float)
        entries: dict[uuid.UUID, ScoredMemory] = {}
        for candidates in (vector_candidates, text_candidates):
            for rank, scored in enumerate(candidates, start=1):
                scores[scored.memory.id] += 1.0 / (RRF_K + rank)
                entries.setdefault(scored.memory.id, scored)
        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], entries[item[0]].memory.created_at),
            reverse=False,
        )
        return [(entries[memory_id], score) for memory_id, score in ranked]

    # ------------------------------------------------------------------
    # context
    # ------------------------------------------------------------------

    async def context(
        self,
        user_id: uuid.UUID,
        *,
        project: str | None = None,
        max_items: int | None = None,
        max_chars: int | None = None,
    ) -> ContextResult:
        """Compact, category-grouped context: global memories plus project ones."""
        normalized_project = normalize_project(project, self._max_project_chars)
        effective_max_items = self._clamp_limit(
            max_items, self._context_default_max_items, self._context_max_items_cap
        )
        effective_max_chars = self._clamp_limit(
            max_chars, self._context_default_max_chars, self._context_max_chars_cap
        )

        # Fetch a wider candidate window than the requested budget so the
        # truncated flag reflects real overflow, not the fetch limit.
        fetch_limit = self._context_max_items_cap
        global_memories = await self._repo.most_important_active(
            user_id, scope="global", limit=fetch_limit
        )
        project_memories = (
            await self._repo.most_important_active(
                user_id, project=normalized_project, limit=fetch_limit
            )
            if normalized_project is not None
            else []
        )
        # The project query also returns global memories; keep one copy of each
        # id, preferring the global listing order for globals.
        seen: set[uuid.UUID] = set()
        ordered: list[Memory] = []
        for memory in (*global_memories, *project_memories):
            if memory.scope == "project" and memory.project != normalized_project:
                continue
            if memory.id in seen:
                continue
            seen.add(memory.id)
            ordered.append(memory)

        grouped: dict[str, list[ContextItem]] = defaultdict(list)
        for memory in ordered:
            grouped[memory.category].append(
                ContextItem(
                    id=memory.id,
                    category=memory.category,
                    content=memory.content,
                    scope=memory.scope,
                    project=memory.project,
                    importance=memory.importance,
                    created_at=memory.created_at,
                )
            )

        groups: list[ContextGroup] = []
        total_items = 0
        used_chars = 0
        truncated = False
        for category in CONTEXT_CATEGORY_ORDER:
            items = grouped.get(category, [])
            kept: list[ContextItem] = []
            for item in items:
                if total_items >= effective_max_items or (
                    used_chars + len(item.content) > effective_max_chars and kept
                ):
                    truncated = True
                    break
                kept.append(item)
                total_items += 1
                used_chars += len(item.content)
            if kept:
                groups.append(ContextGroup(category=category, items=kept))
        if any(grouped.get(c) for c in grouped if c not in CONTEXT_CATEGORY_ORDER):
            truncated = True

        return ContextResult(
            project=normalized_project,
            groups=groups,
            total_items=total_items,
            truncated=truncated or total_items < len(ordered),
        )

    # ------------------------------------------------------------------
    # list_memories
    # ------------------------------------------------------------------

    async def list_memories(
        self,
        user_id: uuid.UUID,
        *,
        scope: str | None = None,
        project: str | None = None,
        category: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ListResult:
        """Enumerate the caller's active memories with bounded pagination."""
        normalized_project = normalize_project(project, self._max_project_chars)
        validated_category = validate_category(category) if category else None
        effective_limit = self._clamp_limit(limit, self._list_default_limit, self._list_max_limit)
        if offset < 0:
            offset = 0
        rows, total = await self._repo.list_active(
            user_id,
            scope=scope,
            project=normalized_project,
            category=validated_category,
            limit=effective_limit,
            offset=offset,
        )
        return ListResult(
            items=[_to_memory_out(row) for row in rows],
            total=total,
            limit=effective_limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # forget
    # ------------------------------------------------------------------

    async def forget(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> ForgetResult:
        """Logical delete; unknown and foreign ids both report not forgotten."""
        forgotten = await self._repo.soft_delete(user_id, memory_id)
        return ForgetResult(id=memory_id, forgotten=forgotten)

    # ------------------------------------------------------------------

    def _clamp_limit(self, requested: int | None, default: int, maximum: int) -> int:
        if requested is None:
            return default
        return max(1, min(int(requested), maximum))


def _to_memory_out(memory: Memory) -> MemoryOut:
    return MemoryOut(
        id=memory.id,
        scope=memory.scope,
        project=memory.project,
        category=memory.category,
        content=memory.content,
        importance=memory.importance,
        source_client=memory.source_client,
        metadata=dict(memory.metadata_ or {}),
        created_at=memory.created_at,
    )
