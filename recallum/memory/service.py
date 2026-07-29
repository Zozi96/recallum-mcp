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
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryGraphResponse,
    MemoryOut,
    RecalledMemory,
    RecallResult,
    RememberResult,
    SimilarMemory,
    UpdateResult,
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
            # Re-stating a memory used to silently drop the new importance and
            # metadata, so raising the importance of something already stored
            # did nothing at all. The content is identical by construction
            # here, so this is bookkeeping, not a new claim: no supersession.
            refreshed = await self._repo.update_attributes(
                user_id,
                existing.id,
                importance=(
                    validated_importance if validated_importance != existing.importance else None
                ),
                category=(
                    validated_category if validated_category != existing.category else None
                ),
                metadata=(
                    validated_metadata
                    if validated_metadata != dict(existing.metadata_ or {})
                    else None
                ),
            )
            return RememberResult(
                memory=_to_memory_out(refreshed if refreshed is not None else existing),
                created=False,
            )

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
                embedding_model=self._embeddings.model,
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
        return RememberResult(
            memory=_to_memory_out(memory),
            created=True,
            similar=await self._similar_to(
                user_id,
                embedding,
                scope=scope,
                project=normalized_project,
                category=validated_category,
                exclude_id=memory.id,
            ),
        )

    async def _similar_to(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        category: str,
        exclude_id: uuid.UUID,
    ) -> list[SimilarMemory]:
        """Pre-existing memories about the same subject as the one just stored.

        Advisory only. A failure here must not fail the write: the memory is
        already committed, and losing the warning is far cheaper than telling
        the caller its memory was not stored when it was.
        """
        if self._limits.similar_max_results == 0:
            return []
        try:
            neighbours = await self._repo.similar_active(
                user_id,
                embedding,
                scope=scope,
                project=project,
                category=category,
                min_similarity=self._limits.similar_min_similarity,
                limit=self._limits.similar_max_results,
                exclude_id=exclude_id,
            )
        except Exception:
            logger.warning("similar-memory check failed; the memory was stored", exc_info=True)
            return []
        return [
            SimilarMemory(
                id=n.memory.id,
                content=n.memory.content,
                category=n.memory.category,
                importance=n.memory.importance,
                similarity=n.score,
                created_at=n.memory.created_at,
            )
            for n in neighbours
        ]

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    async def update(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        content: str | None = None,
        category: str | None = None,
        importance: int | None = None,
        metadata: dict[str, Any] | None = None,
        source_client: str | None = None,
    ) -> UpdateResult:
        """Correct a memory, superseding it when the claim itself changed.

        Two different things wear the same word "update". Changing importance,
        category or metadata is filing: the fact is unchanged, so the row is
        edited and keeps its id. Changing content is a new claim retiring an
        old one, so the original is retired and a new memory takes its place
        with a new id and a fresh embedding, linked back to what it replaced.

        Scope and project are deliberately not editable: moving a memory
        between projects changes its deduplication key, which is a migration
        rather than a correction. Unknown and foreign ids are indistinguishable.
        """
        validated_category = self._validate_category(category) if category is not None else None
        validated_importance = (
            self._validate_importance(importance) if importance is not None else None
        )
        validated_metadata = self._validate_metadata(metadata) if metadata is not None else None

        if content is None:
            updated = await self._repo.update_attributes(
                user_id,
                memory_id,
                importance=validated_importance,
                category=validated_category,
                metadata=validated_metadata,
            )
            if updated is None:
                return UpdateResult(updated=False)
            return UpdateResult(updated=True, memory=_to_memory_out(updated))

        normalized = self._normalize_content(content)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        embedding = await self._embeddings.embed(normalized)
        try:
            replacement = await self._repo.supersede(
                user_id,
                memory_id,
                content=normalized,
                content_hash=digest,
                embedding=embedding,
                embedding_model=self._embeddings.model,
                category=validated_category,
                importance=validated_importance,
                metadata=validated_metadata,
                source_client=source_client,
            )
        except IntegrityError as exc:
            raise MemoryValidationError(
                "another active memory already has that content; forget it first "
                "or update that one instead"
            ) from exc
        if replacement is None:
            return UpdateResult(updated=False)
        return UpdateResult(
            updated=True,
            memory=_to_memory_out(replacement),
            superseded_id=memory_id,
        )

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

        mode = "hybrid"
        query_embedding: list[float] | None = None
        try:
            query_embedding = await self._embeddings.embed(normalized_query)
        except EmbeddingError:
            logger.warning("embedding unavailable for recall; using textual fallback")
            mode = "degraded_textual"

        pools = await self._repo.search_candidates(
            user_id,
            query=normalized_query,
            embedding=query_embedding,
            visibility=visibility,
            category=validated_category,
            limit=candidate_limit,
        )
        vector_candidates = list(pools.vector)
        self._warn_on_embedding_model_drift(vector_candidates)

        fused = self._reciprocal_rank_fusion(vector_candidates, list(pools.text))
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
        """Merge ranked candidate lists with RRF (k=60), importance included.

        Importance enters as a third weighted voter over the candidates the
        retrieval signals already found, never as a way in: a memory nobody
        matched cannot be surfaced by being marked important. Expressing it as a
        rank rather than a score is what keeps it bounded -- RRF only ever reads
        positions, so a 0-to-10 field cannot overpower relevance no matter how
        it is filled in, and ``recall_importance_weight`` sets how much a full
        sweep of the importance ranking is worth against one retrieval signal.

        Recency deliberately does not get a vote. Newer memories superseding
        older ones is a statement about truth, not about relevance, and paying
        for it here would quietly bury long-standing constraints. It stays what
        it was: the tie-break.
        """
        scores: dict[uuid.UUID, float] = defaultdict(float)
        entries: dict[uuid.UUID, ScoredMemory] = {}
        for candidates in (vector_candidates, text_candidates):
            for rank, scored in enumerate(candidates, start=1):
                scores[scored.memory.id] += 1.0 / (RRF_K + rank)
                entries.setdefault(scored.memory.id, scored)

        weight = self._limits.recall_importance_weight
        if weight:
            # Competition ranking: equally important candidates must land on the
            # same rank and so contribute equally. Ordering ties by anything
            # else -- recency being the tempting choice -- would smuggle a
            # second signal in through the tie-break and turn scores that ought
            # to tie into scores that do not.
            by_importance = sorted(entries.values(), key=lambda s: -s.memory.importance)
            rank = 0
            previous_importance: int | None = None
            for position, scored in enumerate(by_importance, start=1):
                if scored.memory.importance != previous_importance:
                    rank = position
                    previous_importance = scored.memory.importance
                scores[scored.memory.id] += weight / (RRF_K + rank)

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

    async def memory_graph(
        self,
        user_id: uuid.UUID,
        *,
        scope: str | None = None,
        project: str | None = None,
        category: str | None = None,
        limit: int | None = None,
    ) -> MemoryGraphResponse:
        """Build a bounded graph while preserving nodes without strong edges."""
        normalized_project = self._normalize_project(project)
        visibility = MemoryVisibility.from_filters(scope=scope, project=normalized_project)
        validated_category = self._validate_category(category) if category else None
        effective_limit = self._clamp_limit(
            limit, self._limits.graph_max_nodes, self._limits.graph_max_nodes
        )
        snapshot = await self._repo.graph_snapshot(
            user_id,
            visibility=visibility,
            category=validated_category,
            limit=effective_limit,
            min_similarity=self._limits.graph_min_similarity,
        )
        degree: defaultdict[uuid.UUID, int] = defaultdict(int)
        edges: list[MemoryGraphEdge] = []
        for pair in sorted(
            snapshot.pairs,
            key=lambda pair: (-pair.similarity, str(pair.source_id), str(pair.target_id)),
        ):
            if (
                degree[pair.source_id] >= self._limits.graph_max_neighbours
                or degree[pair.target_id] >= self._limits.graph_max_neighbours
            ):
                continue
            source_id, target_id = sorted((pair.source_id, pair.target_id), key=str)
            edges.append(
                MemoryGraphEdge(
                    source_id=source_id,
                    target_id=target_id,
                    similarity=pair.similarity,
                )
            )
            degree[source_id] += 1
            degree[target_id] += 1
        return MemoryGraphResponse(
            nodes=[
                MemoryGraphNode(
                    id=memory.id,
                    scope=memory.scope,
                    project=memory.project,
                    category=memory.category,
                    content=memory.content,
                    importance=memory.importance,
                    created_at=memory.created_at,
                )
                for memory in snapshot.memories
            ],
            edges=edges,
            total=snapshot.total,
            truncated=snapshot.total > len(snapshot.memories),
            model_mismatch=snapshot.model_mismatch,
        )

    # ------------------------------------------------------------------
    # forget
    # ------------------------------------------------------------------

    async def forget(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> ForgetResult:
        """Logical delete; unknown and foreign ids both report not forgotten."""
        forgotten = await self._repo.soft_delete(user_id, memory_id)
        return ForgetResult(id=memory_id, forgotten=forgotten)

    # ------------------------------------------------------------------

    def _warn_on_embedding_model_drift(self, candidates: list[ScoredMemory]) -> None:
        """Warn when ranked vectors came from a model that is no longer configured.

        Embeddings from different models share no coordinate space, so after
        ``RECALLUM__OLLAMA__MODEL`` changes, cosine similarity over older rows
        is noise -- with nothing to notice it by.

        Checked here rather than at startup because ``memories`` has RLS forced
        and the app role is NOBYPASSRLS: there is deliberately no way to
        aggregate across users, so the only place holding both a user's rows and
        the configured model is a request. Reading the already-fetched rows
        keeps it free of extra queries, and it fires exactly when a stale vector
        actually influences a ranking. It warns rather than filtering, because
        silently hiding a user's memories is the worse failure.

        A NULL model means the row predates provenance tracking, which is not
        evidence of a mismatch -- every row in a database migrated from an
        earlier version looks like this. Treating unknown as stale would fire on
        every recall until the whole corpus is rewritten, so only a positively
        different model counts.
        """
        configured = self._embeddings.model
        stale = {
            candidate.memory.embedding_model
            for candidate in candidates
            if candidate.memory.embedding_model not in (None, configured)
        }
        if not stale:
            return
        logger.warning(
            "recall ranked vectors produced by %s but %r is configured; their "
            "similarity scores are unreliable until re-embedded",
            ", ".join(sorted(stale)),
            configured,
        )

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
