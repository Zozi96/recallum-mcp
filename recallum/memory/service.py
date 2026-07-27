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

import hashlib
import json
import logging
import re
import unicodedata
import uuid
from collections import defaultdict
from typing import Any, Literal, get_args

from sqlalchemy.exc import IntegrityError

from recallum.db.models import Memory
from recallum.db.repositories.memory_repo import MAX_CANDIDATES, MemoryRepository, ScoredMemory
from recallum.embeddings.ollama import EmbeddingError, OllamaEmbeddingClient
from recallum.memory import MemoryValidationError, MemoryVisibility
from recallum.memory.context import SessionContextBudget
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import (
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

Category = Literal["preference", "decision", "constraint", "fact"]
CATEGORIES: tuple[str, ...] = get_args(Category)
_WHITESPACE = re.compile(r"\s+")


class MemoryService:
    """Coordinates validation, embeddings, retrieval and persistence."""

    def __init__(
        self,
        repository: MemoryRepository,
        embeddings: OllamaEmbeddingClient,
        limits: MemoryLimits | None = None,
    ) -> None:
        self._repo = repository
        self._embeddings = embeddings
        self._limits = limits if limits is not None else MemoryLimits()

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
        normalized = self._normalize_content(content)
        normalized_project = self._normalize_project(project)
        validated_category = self._validate_category(category)
        validated_importance = self._validate_importance(importance)
        validated_metadata = self._validate_metadata(metadata)
        scope = "project" if normalized_project is not None else "global"
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

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
        normalized_query = self._normalize_content(query)
        normalized_project = self._normalize_project(project)
        visibility = MemoryVisibility.from_filters(scope=scope, project=normalized_project)
        validated_category = self._validate_category(category) if category else None
        effective_limit = self._clamp_limit(
            limit, self._limits.recall_default_limit, self._limits.recall_max_limit
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
                    visibility=visibility,
                    category=validated_category,
                    limit=candidate_limit,
                )
            )

        text_candidates = list(
            await self._repo.search_text(
                user_id,
                normalized_query,
                visibility=visibility,
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
            scores.items(), key=lambda item: entries[item[0]].memory.created_at, reverse=True
        )
        ranked.sort(key=lambda item: item[1], reverse=True)
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
        normalized_project = self._normalize_project(project)
        effective_max_items = self._clamp_limit(
            max_items, self._limits.context_default_max_items, self._limits.context_max_items_cap
        )
        effective_max_chars = self._clamp_limit(
            max_chars, self._limits.context_default_max_chars, self._limits.context_max_chars_cap
        )

        # Fetch one row beyond the largest snapshot the caller could ask for.
        # A requested budget can never exceed the cap, so an extra row is
        # enough to tell "this is everything" from "there was more", and
        # ``truncated`` stops being a statement about the fetch window.
        fetch_limit = self._limits.context_max_items_cap + 1
        global_memories = await self._repo.most_important_active(
            user_id, visibility=MemoryVisibility.global_only(), limit=fetch_limit
        )
        project_memories = (
            await self._repo.most_important_active(
                user_id,
                visibility=MemoryVisibility.project_only(normalized_project),
                limit=fetch_limit,
            )
            if normalized_project is not None
            else []
        )
        budget = SessionContextBudget(
            max_items=effective_max_items, max_chars=effective_max_chars
        )
        return budget.assemble(
            global_memories, project_memories, project=normalized_project
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
        normalized_project = self._normalize_project(project)
        visibility = MemoryVisibility.from_filters(scope=scope, project=normalized_project)
        validated_category = self._validate_category(category) if category else None
        effective_limit = self._clamp_limit(
            limit, self._limits.list_default_limit, self._limits.list_max_limit
        )
        offset = max(0, min(int(offset), self._limits.list_max_offset))
        rows, total = await self._repo.list_active(
            user_id,
            visibility=visibility,
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

    def _normalize_content(self, content: str) -> str:
        if content is None:
            raise MemoryValidationError("content must not be empty")
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", content)).strip()
        if not normalized:
            raise MemoryValidationError("content must not be empty")
        if len(normalized) > self._limits.max_content_chars:
            raise MemoryValidationError(
                f"content exceeds {self._limits.max_content_chars} characters"
            )
        return normalized

    def _normalize_project(self, project: str | None) -> str | None:
        if project is None:
            return None
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", project)).strip()
        if not normalized:
            return None
        if len(normalized) > self._limits.max_project_chars:
            raise MemoryValidationError(
                f"project exceeds {self._limits.max_project_chars} characters"
            )
        return normalized

    def _validate_category(self, category: str) -> Category:
        if category not in CATEGORIES:
            raise MemoryValidationError(
                f"unknown category '{category}'; expected one of {', '.join(CATEGORIES)}"
            )
        return category  # type: ignore[return-value]

    def _validate_importance(self, importance: int) -> int:
        if not isinstance(importance, int) or isinstance(importance, bool):
            raise MemoryValidationError("importance must be an integer")
        if not 0 <= importance <= 10:
            raise MemoryValidationError("importance must be between 0 and 10")
        return importance

    def _validate_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any]:
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise MemoryValidationError("metadata must be a JSON object")
        if len(metadata) > self._limits.max_metadata_keys:
            raise MemoryValidationError(
                f"metadata exceeds {self._limits.max_metadata_keys} keys"
            )
        for key, value in metadata.items():
            if not isinstance(key, str) or not key:
                raise MemoryValidationError("metadata keys must be non-empty strings")
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                raise MemoryValidationError(
                    f"metadata value for '{key}' must be a JSON primitive"
                )
        serialized = json.dumps(metadata, ensure_ascii=True, sort_keys=True)
        if len(serialized.encode("utf-8")) > self._limits.max_metadata_bytes:
            raise MemoryValidationError(
                f"metadata exceeds {self._limits.max_metadata_bytes} bytes"
            )
        return dict(metadata)


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
