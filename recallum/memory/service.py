"""Memory service: remember, recall, context, get, list and forget.

Business rules implemented here:
- ``remember`` embeds before persisting; an exact active duplicate returns the
  existing row instead of inserting a second one.
- ``recall`` fuses vector and textual candidates with Reciprocal Rank Fusion
  and degrades to textual-only (flagged) when Ollama cannot embed the query.
- ``context`` produces a compact, category-grouped budget-aware snapshot.
- ``get`` is the by-id read behind truncated context items and verification.
- ``forget`` is a logical delete; foreign and unknown ids are indistinguishable.
- ``reembed_stale`` restamps vectors in place after an embedding-model change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, get_args

from sqlalchemy.exc import IntegrityError

from recallum.boundary_types import StrictImportance, StrictNonNegativeOffset, StrictPositiveLimit
from recallum.db.models import Memory
from recallum.db.repositories.memory_repo import (
    MAX_CANDIDATES,
    BucketMismatchError,
    MemoryRepository,
    ProfileGenerationConflict,
    ScoredMemory,
    _cap_pairs_by_degree,
)
from recallum.diagnostics import EMBEDDING_UNAVAILABLE_MESSAGE, record_sanitized_failure
from recallum.embeddings.ollama import EmbeddingError, OllamaEmbeddingClient
from recallum.memory import MemoryValidationError, MemoryVisibility
from recallum.memory.context import SessionContextBudget
from recallum.memory.language import LANGUAGE_WARNING, looks_non_english
from recallum.memory.limits import MemoryLimits
from recallum.memory.profile_select import (
    apply_profile_budget,
    items_from_stored,
    profile_content_hash,
    select_dynamic_slice,
    select_profile_slices,
)
from recallum.memory.schemas import (
    ContextResult,
    ForgetResult,
    GetResult,
    ListResult,
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryGraphResponse,
    MemoryOut,
    MergeResult,
    ProfileBlock,
    ProfileItem,
    ReassignResult,
    RecalledMemory,
    RecallResult,
    ReconfirmResult,
    RelatedMemoriesResult,
    RelatedMemory,
    RememberBatchItem,
    RememberBatchItemOutcome,
    RememberBatchResult,
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
        importance: StrictImportance = 5,
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
        language_warning = self._language_warning(normalized)

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
                category=(validated_category if validated_category != existing.category else None),
                metadata=(
                    validated_metadata
                    if validated_metadata != dict(existing.metadata_ or {})
                    else None
                ),
            )
            # It IS a reconfirmation, though: the claim was just observed to
            # still hold, and readers use that stamp to judge freshness.
            reconfirmed = await self._repo.mark_reconfirmed(user_id, existing.id)
            current = next(row for row in (reconfirmed, refreshed, existing) if row is not None)
            await self._rebuild_profiles_for_memory(user_id, current)
            return RememberResult(
                memory=_to_memory_out(current),
                created=False,
                language_warning=language_warning,
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
                # A concurrent insert of identical content is a reconfirmation
                # from this caller's point of view: stamp it like the dedup path.
                reconfirmed = await self._repo.mark_reconfirmed(user_id, racing.id)
                current = reconfirmed if reconfirmed is not None else racing
                await self._rebuild_profiles_for_memory(user_id, current)
                return RememberResult(
                    memory=_to_memory_out(current),
                    created=False,
                    language_warning=language_warning,
                )
            raise
        await self._rebuild_profiles_for_memory(user_id, memory)
        return RememberResult(
            memory=_to_memory_out(memory),
            created=True,
            similar=await self._similar_to(
                user_id,
                embedding,
                scope=scope,
                project=normalized_project,
                exclude_id=memory.id,
            ),
            language_warning=language_warning,
        )

    def _language_warning(self, normalized: str) -> str | None:
        """Advisory hint that ``normalized`` content looks non-English.

        Pure and cheap, but guarded the same way ``_similar_to`` guards its
        network call: an advisory must never fail or block the write it rides
        along on, no matter how the heuristic misbehaves.
        """
        try:
            return LANGUAGE_WARNING if looks_non_english(normalized) else None
        except Exception:
            logger.warning("language heuristic failed; the memory was stored", exc_info=True)
            return None

    async def _similar_to(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        exclude_id: uuid.UUID,
    ) -> list[SimilarMemory]:
        """Pre-existing memories about the same subject as the one just stored.

        Deliberately blind to category: agents miscategorize, and a fact that
        near-duplicates a decision is exactly the conflict worth surfacing.
        Each hit carries its category so a filing mismatch is readable.

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
                embedding_model=self._embeddings.model,
                scope=scope,
                project=project,
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
                reconfirmed_at=n.memory.reconfirmed_at,
            )
            for n in neighbours
        ]

    async def remember_batch(
        self,
        user_id: uuid.UUID,
        *,
        items: Sequence[RememberBatchItem],
        source_client: str | None = None,
    ) -> RememberBatchResult:
        """Store up to ``batch_max_items`` memories with per-item outcomes.

        Exists so the end-of-session capture scan costs one round trip instead
        of N. Every item goes through exactly the same validation, dedup and
        similar-advisory path as ``remember``. Items succeed or fail alone
        (partial success), but an empty or oversized batch is rejected whole
        before anything persists. Domain and embedding failures stay per-item;
        infrastructure failures propagate and fail the call.
        """
        if not items:
            raise MemoryValidationError("batch must contain at least one item")
        if len(items) > self._limits.batch_max_items:
            raise MemoryValidationError(f"batch exceeds {self._limits.batch_max_items} items")
        outcomes: list[RememberBatchItemOutcome] = []
        for item in items:
            try:
                result = await self.remember(
                    user_id,
                    content=item.content,
                    category=item.category,
                    project=item.project,
                    importance=item.importance,
                    metadata=item.metadata,
                    source_client=source_client,
                )
            except MemoryValidationError as exc:
                outcomes.append(RememberBatchItemOutcome(error=str(exc)))
                continue
            except EmbeddingError as exc:
                record_sanitized_failure(logger, exc, message="Memory batch item failure")
                outcomes.append(RememberBatchItemOutcome(error=EMBEDDING_UNAVAILABLE_MESSAGE))
                continue
            outcomes.append(
                RememberBatchItemOutcome(
                    created=result.created,
                    memory=result.memory,
                    similar=result.similar,
                    language_warning=result.language_warning,
                )
            )
        return RememberBatchResult(
            results=outcomes,
            stored=sum(1 for o in outcomes if o.memory is not None and o.created),
            deduplicated=sum(1 for o in outcomes if o.memory is not None and not o.created),
            failed=sum(1 for o in outcomes if o.error is not None),
        )

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
        importance: StrictImportance | None = None,
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
            await self._rebuild_profiles_for_memory(user_id, updated)
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
        await self._rebuild_profiles_for_memory(user_id, replacement)
        return UpdateResult(
            updated=True,
            memory=_to_memory_out(replacement),
            superseded_id=memory_id,
        )

    # ------------------------------------------------------------------
    # merge
    # ------------------------------------------------------------------

    async def merge(
        self,
        user_id: uuid.UUID,
        *,
        source_ids: Sequence[uuid.UUID],
        content: str,
        category: str,
        importance: StrictImportance | None = None,
        metadata: dict[str, Any] | None = None,
        source_client: str | None = None,
    ) -> MergeResult:
        """Consolidate several memories into one, keeping the whole trail.

        The missing move in the reconcile loop: ``similar`` surfaces
        overlapping memories at write time, but the only responses were 1:1
        ``update`` or destructive ``forget``, so ignored near-duplicates
        accumulated forever. Merge retires every source and links each to
        the one consolidated replacement -- recoverable via ``get`` with
        history, never a deletion. Scope and project come from the sources
        and must agree across them; ``importance`` defaults to the loudest
        source, because a consolidated claim is at least as important as its
        strongest part. For restatements and refinements only: resolving a
        contradiction is an ``update`` of the wrong memory, not a merge.
        """
        unique_ids = list(dict.fromkeys(source_ids))
        if len(unique_ids) != len(list(source_ids)):
            raise MemoryValidationError("source ids must be unique")
        if len(unique_ids) < 2:
            raise MemoryValidationError("merging needs at least two source memories")
        if len(unique_ids) > self._limits.merge_max_sources:
            raise MemoryValidationError(f"merge exceeds {self._limits.merge_max_sources} sources")
        normalized = self._normalize_content(content)
        validated_category = self._validate_category(category)
        validated_importance = (
            self._validate_importance(importance) if importance is not None else None
        )
        validated_metadata = self._validate_metadata(metadata)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        # Embed before touching rows: a memory without a vector is never stored.
        embedding = await self._embeddings.embed(normalized)
        try:
            outcome = await self._repo.merge_memories(
                user_id,
                unique_ids,
                content=normalized,
                content_hash=digest,
                embedding=embedding,
                embedding_model=self._embeddings.model,
                category=validated_category,
                importance=validated_importance,
                source_client=source_client,
                metadata=validated_metadata,
            )
        except BucketMismatchError as exc:
            raise MemoryValidationError(
                "sources span different scopes or projects; merge within one "
                "bucket -- moving memories between projects is a supervised "
                "reassign-project migration"
            ) from exc
        except IntegrityError as exc:
            raise MemoryValidationError(
                "another active memory already has that content; include it "
                "in the merge or update it instead"
            ) from exc
        if outcome is None:
            return MergeResult(merged=False)
        replacement, retired = outcome
        await self._rebuild_profiles_for_memory(user_id, replacement)
        return MergeResult(
            merged=True,
            memory=_to_memory_out(replacement),
            superseded_ids=retired,
            similar=await self._similar_to(
                user_id,
                embedding,
                scope=replacement.scope,
                project=replacement.project,
                exclude_id=replacement.id,
            ),
        )

    # ------------------------------------------------------------------
    # reassign project
    # ------------------------------------------------------------------

    async def reassign_project(
        self,
        user_id: uuid.UUID,
        *,
        from_project: str,
        to_project: str,
    ) -> ReassignResult:
        """Move every active memory from one project key to another.

        Deliberately absent from the MCP surface: changing a memory's project
        changes its deduplication key, which makes this a person-supervised
        migration (fixing key fragmentation after a move, fork or rename), not
        an agent correction. Contents that already exist active under the
        target key are skipped and reported as conflicts.
        """
        normalized_from = self._normalize_project(from_project)
        normalized_to = self._normalize_project(to_project)
        if normalized_from is None or normalized_to is None:
            raise MemoryValidationError("both project keys are required")
        if normalized_from == normalized_to:
            raise MemoryValidationError("source and target project keys are identical")
        try:
            moved, conflicts = await self._repo.reassign_project(
                user_id, from_project=normalized_from, to_project=normalized_to
            )
        except IntegrityError as exc:
            raise MemoryValidationError(
                "a concurrent write created a conflicting memory in the target "
                "project; retry the migration"
            ) from exc
        if moved:
            await self._rebuild_profiles_for_keys(user_id, [normalized_from, normalized_to])
        return ReassignResult(
            from_project=normalized_from,
            to_project=normalized_to,
            moved=moved,
            conflicts=list(conflicts),
        )

    # ------------------------------------------------------------------
    # reembed
    # ------------------------------------------------------------------

    async def reembed_stale(self, user_id: uuid.UUID, *, batch_size: int = 50) -> tuple[int, int]:
        """Re-embed active memories whose vector provenance is stale.

        Covers rows embedded by another model and rows predating provenance
        tracking; both are outside the configured coordinate space, so the
        vector leg either excludes or cannot trust them until restamped. In
        place by design: the claim itself is unchanged, so content, hash and
        id all stay -- this is maintenance, not supersession. Keyset
        pagination advances past rows whose embedding keeps failing, so a
        partial Ollama outage stalls nothing; rerunning is idempotent and
        picks up whatever remains. Returns ``(reembedded, failed)``.

        Deliberately absent from the MCP surface: a model swap is an operator
        event, remedied by ``recallum-admin reembed``, not an agent decision.
        """
        model = self._embeddings.model
        reembedded = 0
        failed = 0
        after: uuid.UUID | None = None
        while True:
            rows = await self._repo.stale_embeddings_batch(
                user_id, model=model, after=after, limit=max(1, batch_size)
            )
            if not rows:
                return reembedded, failed
            for row in rows:
                after = row.id
                try:
                    vector = await self._embeddings.embed(row.content)
                except EmbeddingError:
                    failed += 1
                    continue
                # False means the row retired mid-run; neither counter moves.
                if await self._repo.replace_embedding(
                    user_id, row.id, embedding=vector, model=model
                ):
                    reembedded += 1

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
        limit: StrictPositiveLimit | None = None,
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
            embedding_model=self._embeddings.model,
            visibility=visibility,
            category=validated_category,
            limit=candidate_limit,
            trigram_min_word_similarity=self._trigram_min_similarity(),
        )

        fused = self._reciprocal_rank_fusion(
            list(pools.vector), list(pools.text), list(pools.trigram)
        )
        results = [
            RecalledMemory(**_to_memory_out(scored.memory).model_dump(), score=score)
            for scored, score in fused[:effective_limit]
        ]
        await self._record_recalled(user_id, [result.id for result in results])
        return RecallResult(query=normalized_query, mode=mode, results=results)

    def _reciprocal_rank_fusion(
        self,
        vector_candidates: list[ScoredMemory],
        text_candidates: list[ScoredMemory],
        trigram_candidates: list[ScoredMemory] | None = None,
    ) -> list[tuple[ScoredMemory, float]]:
        """Merge ranked candidate lists with RRF (k=60), importance included.

        The retrieval voters are the semantic leg and the exact-text leg at
        full strength, plus the fuzzy trigram leg at
        ``recall_trigram_weight``: it is a safety net for typos, identifier
        fragments and dictionary-mangled words, so it may surface rows the
        primary signals never found and break ties, but never outvote a
        genuine match. At weight 0.0 its candidates are ignored entirely --
        a pool that cannot vote must not smuggle rows into the importance
        ranking either.

        Importance enters as a further weighted voter over the candidates the
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

        Usage (``recall_count``) is wired as one more voter under the same
        competition-ranking rules, but ships with ``recall_usage_weight`` at
        0.0: being served often is a feedback loop (rich get richer), so it
        may only influence ranking after real usage data justifies a weight.
        """
        weighted_pools: list[tuple[list[ScoredMemory], float]] = [
            (vector_candidates, 1.0),
            (text_candidates, 1.0),
            (trigram_candidates or [], self._limits.recall_trigram_weight),
        ]
        scores: dict[uuid.UUID, float] = defaultdict(float)
        entries: dict[uuid.UUID, ScoredMemory] = {}
        for candidates, pool_weight in weighted_pools:
            if not pool_weight:
                continue
            for rank, scored in enumerate(candidates, start=1):
                scores[scored.memory.id] += pool_weight / (RRF_K + rank)
                entries.setdefault(scored.memory.id, scored)

        # Importance and usage are the same competition-rank voter with
        # different keys and weights. Ties share a rank so a secondary
        # signal cannot sneak in through the sort order.
        self._add_competition_vote(
            entries,
            scores,
            key=lambda scored: scored.memory.importance,
            weight=self._limits.recall_importance_weight,
        )
        self._add_competition_vote(
            entries,
            scores,
            key=lambda scored: scored.memory.recall_count or 0,
            weight=self._limits.recall_usage_weight,
        )

        ranked = sorted(
            scores.items(), key=lambda item: entries[item[0]].memory.created_at, reverse=True
        )
        ranked.sort(key=lambda item: item[1], reverse=True)
        return [(entries[memory_id], score) for memory_id, score in ranked]

    def _add_competition_vote(
        self,
        entries: dict[uuid.UUID, ScoredMemory],
        scores: dict[uuid.UUID, float],
        *,
        key: Callable[[ScoredMemory], int],
        weight: float,
    ) -> None:
        """Add one RRF voter over already-found candidates, ties sharing a rank."""
        if not weight:
            return
        ordered = sorted(entries.values(), key=lambda scored: -key(scored))
        rank = 0
        previous: int | None = None
        for position, scored in enumerate(ordered, start=1):
            value = key(scored)
            if value != previous:
                rank = position
                previous = value
            scores[scored.memory.id] += weight / (RRF_K + rank)

    # ------------------------------------------------------------------
    # context
    # ------------------------------------------------------------------

    async def context(
        self,
        user_id: uuid.UUID,
        *,
        project: str | None = None,
        focus: str | None = None,
        max_items: StrictPositiveLimit | None = None,
        max_chars: StrictPositiveLimit | None = None,
    ) -> ContextResult:
        """Compact context: always-on profile first, then category snapshot.

        ``focus`` biases the categorized snapshot toward the task at hand:
        hybrid matches are added to importance-ranked pools -- never
        displacing the profile block -- before the remaining budget is applied.

        The read observes one database snapshot (``context_snapshot``):
        profile row, generation, importance pools, dynamic candidates, the
        visible total and the focus pools all come from the same RLS-pinned
        transaction. The focus embedding (HTTP to Ollama) and the post-hoc
        usage recording stay outside that transaction.
        """
        normalized_project = self._normalize_project(project)
        normalized_focus = (
            self._normalize_content(focus) if focus is not None and focus.strip() else None
        )
        effective_max_items = self._clamp_limit(
            max_items, self._limits.context_default_max_items, self._limits.context_max_items_cap
        )
        effective_max_chars = self._clamp_limit(
            max_chars, self._limits.context_default_max_chars, self._limits.context_max_chars_cap
        )

        # Embed before the snapshot: Ollama is HTTP and must not hold the
        # database transaction open. Failure degrades the focus to textual.
        embedding: list[float] | None = None
        if normalized_focus is not None:
            try:
                embedding = await self._embeddings.embed(normalized_focus)
            except EmbeddingError:
                logger.warning("embedding unavailable for context focus; using textual fallback")

        visibility = (
            MemoryVisibility.global_only()
            if normalized_project is None
            else MemoryVisibility.from_filters(scope=None, project=normalized_project)
        )
        snapshot = await self._repo.context_snapshot(
            user_id,
            project=normalized_project,
            visibility=visibility,
            category=None,
            top_limit=self._limits.context_max_items_cap + 1,
            candidate_limit=min(MAX_CANDIDATES, max(self._limits.context_focus_limit * 3, 10)),
            query=normalized_focus,
            embedding=embedding,
            embedding_model=self._embeddings.model,
            trigram_min_word_similarity=self._trigram_min_similarity(),
            static_limit=self._limits.profile_static_max_items,
            dynamic_limit=self._limits.profile_dynamic_max_items,
            dynamic_since=datetime.now(UTC)
            - timedelta(days=self._limits.profile_dynamic_window_days),
            static_min_importance=self._limits.profile_static_min_importance,
        )

        try:
            if snapshot.profile is None or snapshot.profile.generation != snapshot.generation:
                # Cold path: no materialized static row, or a corpus mutation
                # made it stale. The rebuild CAS runs outside the snapshot
                # transaction; the returned block carries its own live dynamic.
                profile_block = await self.rebuild_profile(user_id, project=normalized_project)
            else:
                static = items_from_stored(snapshot.profile.static_items)
                static_ids = {item.id for item in static}
                dynamic = select_dynamic_slice(
                    snapshot.dynamic_candidates,
                    limits=self._limits,
                    now=datetime.now(UTC),
                    exclude_ids=static_ids,
                )
                profile_block = self._profile_block_from_row(
                    snapshot.profile, project=normalized_project, dynamic=dynamic
                )
            profile_block = self._cap_profile_block(
                profile_block,
                max_items=min(effective_max_items, self._limits.profile_context_max_items),
                max_chars=min(effective_max_chars, self._limits.profile_context_max_chars),
            )
        except Exception:
            logger.warning("profile assembly failed; context continues", exc_info=True)
            profile_block = ProfileBlock(available=False, project=normalized_project)

        profile_count = len(profile_block.static) + len(profile_block.dynamic)
        remaining_items = max(0, effective_max_items - profile_count)
        remaining_chars = max(
            0,
            effective_max_chars
            - sum(len(item.content) for item in (*profile_block.static, *profile_block.dynamic)),
        )

        focus_memories: list[Memory] = []
        if normalized_focus is not None:
            fused = self._reciprocal_rank_fusion(
                list(snapshot.focus.vector),
                list(snapshot.focus.text),
                list(snapshot.focus.trigram),
            )
            focus_memories = [
                scored.memory for scored, _ in fused[: self._limits.context_focus_limit]
            ]

        budget = SessionContextBudget(
            max_items=remaining_items,
            max_chars=remaining_chars,
            truncate_floor=self._limits.context_truncate_floor,
        )
        result = budget.assemble(
            list(snapshot.global_top),
            list(snapshot.project_top),
            focus_memories,
            project=normalized_project,
            total_available=snapshot.total_available,
            focus=normalized_focus,
            stale_before=self._stale_cutoff(),
            exclude_ids=set(profile_block.source_memory_ids),
            profile_item_count=profile_count,
        )
        result = result.model_copy(update={"profile": profile_block})
        served = [
            *[item.id for item in profile_block.static],
            *[item.id for item in profile_block.dynamic],
            *[item.id for group in result.groups for item in group.items],
        ]
        await self._record_context_served(user_id, served)
        return result

    def _cap_profile_block(
        self, block: ProfileBlock, *, max_items: int, max_chars: int
    ) -> ProfileBlock:
        """Apply the caller's reserved profile budget to an assembled block.

        The digest is recomputed over the capped slices so the served
        integrity fingerprint matches exactly what the caller received.
        """
        static, dynamic, ids = apply_profile_budget(
            block.static, block.dynamic, max_items=max_items, max_chars=max_chars
        )
        return ProfileBlock(
            available=block.available,
            project=block.project,
            static=static,
            dynamic=dynamic,
            source_memory_ids=ids,
            digest=profile_content_hash(static, dynamic),
            built_at=block.built_at,
        )

    def _trigram_min_similarity(self) -> float | None:
        """The trigram leg's threshold, or None when its weight disables it."""
        if not self._limits.recall_trigram_weight:
            return None
        return self._limits.trigram_min_word_similarity

    async def _record_recalled(self, user_id: uuid.UUID, memory_ids: list[uuid.UUID]) -> None:
        """Count recall hits; a failure here never fails the read."""
        if not memory_ids:
            return
        try:
            await self._repo.mark_recalled(user_id, memory_ids)
        except Exception:
            logger.warning("usage recording failed; the result is unaffected", exc_info=True)

    async def _record_context_served(self, user_id: uuid.UUID, memory_ids: list[uuid.UUID]) -> None:
        """Count snapshot serves, apart from recall hits.

        Snapshots select mostly by importance, so folding their serves into
        ``recall_count`` would pre-poison the usage voter with an importance
        echo -- the rich-get-richer loop it is gated against. A failure here
        never fails the read.
        """
        if not memory_ids:
            return
        try:
            await self._repo.mark_seen_in_context(user_id, memory_ids)
        except Exception:
            logger.warning("usage recording failed; the result is unaffected", exc_info=True)

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
        stale: bool | None = None,
        limit: StrictPositiveLimit | None = None,
        offset: StrictNonNegativeOffset = 0,
    ) -> ListResult:
        """Enumerate the caller's active memories with bounded pagination.

        ``stale=True`` is the verification queue: only memories whose last
        confirmation (``reconfirmed_at``, else ``created_at``) is older than
        ``stale_after_days``. ``stale=False`` keeps only fresh ones; ``None``
        does not filter. This is the consumer for the freshness signals the
        schema records: without it, finding what needs re-verification meant
        paging everything and doing date math by hand.
        """
        normalized_project = self._normalize_project(project)
        visibility = MemoryVisibility.from_filters(scope=scope, project=normalized_project)
        validated_category = self._validate_category(category) if category else None
        effective_limit = self._clamp_limit(
            limit, self._limits.list_default_limit, self._limits.list_max_limit
        )
        if not isinstance(offset, int) or isinstance(offset, bool):
            raise MemoryValidationError("offset must be an integer")
        offset = max(0, min(offset, self._limits.list_max_offset))
        cutoff = self._stale_cutoff() if stale is not None else None
        rows, total = await self._repo.list_active(
            user_id,
            visibility=visibility,
            category=validated_category,
            limit=effective_limit,
            offset=offset,
            stale_before=cutoff if stale else None,
            fresh_since=cutoff if stale is False else None,
        )
        return ListResult(
            items=[_to_memory_out(row) for row in rows],
            total=total,
            limit=effective_limit,
            offset=offset,
        )

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    async def get(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        include_history: bool = False,
    ) -> GetResult:
        """Fetch one active memory, optionally with the chain it superseded.

        The by-id read that ``context`` items point at: truncated snapshot
        entries carry an id, and this is how their full text is retrieved
        without re-running retrieval. Also the cheap re-verification read for
        an old memory before trusting it. Unknown, foreign and retired ids
        are indistinguishable (``found`` is False), matching ``update`` and
        ``forget``. ``history`` lists retired predecessors oldest-first.
        Deliberately not counted as usage: fetching by id is bookkeeping,
        not evidence the memory matched anything.
        """
        memory = await self._repo.get_active(user_id, memory_id)
        if memory is None:
            return GetResult(found=False)
        history: list[MemoryOut] | None = None
        if include_history:
            chain = await self._repo.history(user_id, memory_id)
            history = [_to_memory_out(row) for row in (chain or ())]
        return GetResult(found=True, memory=_to_memory_out(memory), history=history)

    async def memory_graph(
        self,
        user_id: uuid.UUID,
        *,
        scope: str | None = None,
        project: str | None = None,
        category: str | None = None,
        limit: StrictPositiveLimit | None = None,
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
            max_neighbours=self._limits.graph_max_neighbours,
            scalable_enabled=self._limits.graph_scalable_enabled,
            scalable_min_nodes=self._limits.graph_scalable_min_nodes,
        )
        edges: list[MemoryGraphEdge] = []
        for pair in _cap_pairs_by_degree(snapshot.pairs, self._limits.graph_max_neighbours):
            source_id, target_id = sorted((pair.source_id, pair.target_id), key=str)
            edges.append(
                MemoryGraphEdge(
                    source_id=source_id,
                    target_id=target_id,
                    similarity=pair.similarity,
                )
            )
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
            edge_total=snapshot.edge_total,
            edges_truncated=snapshot.edge_total > len(edges),
        )

    async def related_memories(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        limit: StrictPositiveLimit | None = None,
    ) -> RelatedMemoriesResult:
        """Return a bounded thematic neighbourhood for one active seed."""
        effective_limit = self._clamp_limit(
            limit, self._limits.graph_max_neighbours, self._limits.graph_max_neighbours
        )
        neighbours = await self._repo.related_to(
            user_id,
            memory_id,
            limit=effective_limit,
            min_similarity=self._limits.graph_min_similarity,
        )
        return RelatedMemoriesResult(
            memory_id=memory_id,
            related=[
                RelatedMemory(
                    id=item.memory.id,
                    content=item.memory.content,
                    category=item.memory.category,
                    scope=item.memory.scope,
                    project=item.memory.project,
                    similarity=item.score,
                )
                for item in neighbours
            ],
        )

    # ------------------------------------------------------------------
    # forget
    # ------------------------------------------------------------------

    async def reconfirm(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> ReconfirmResult:
        """Stamp freshness on an active memory without rewriting its content."""
        stamped = await self._repo.mark_reconfirmed(user_id, memory_id)
        if stamped is None:
            return ReconfirmResult(reconfirmed=False)
        await self._rebuild_profiles_for_memory(user_id, stamped)
        return ReconfirmResult(reconfirmed=True, memory=_to_memory_out(stamped))

    async def forget(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> ForgetResult:
        """Logical delete; unknown and foreign ids both report not forgotten."""
        existing = await self._repo.get_active(user_id, memory_id)
        forgotten = await self._repo.soft_delete(user_id, memory_id)
        if forgotten and existing is not None:
            await self._rebuild_profiles_for_memory(user_id, existing)
        return ForgetResult(id=memory_id, forgotten=forgotten)

    # ------------------------------------------------------------------
    # profiles
    # ------------------------------------------------------------------

    async def get_profile(self, user_id: uuid.UUID, *, project: str | None = None) -> ProfileBlock:
        """Load or lazily rebuild the materialized profile for a key."""
        normalized = self._normalize_project(project)
        try:
            return await self._ensure_profile(user_id, project=normalized)
        except Exception:
            logger.warning("profile read failed; returning unavailable", exc_info=True)
            return ProfileBlock(available=False, project=normalized)

    async def rebuild_profile(
        self, user_id: uuid.UUID, *, project: str | None = None
    ) -> ProfileBlock:
        """Force-rebuild one profile key with a bounded generation CAS retry."""
        normalized = self._normalize_project(project)
        visibility = (
            MemoryVisibility.global_only()
            if normalized is None
            else MemoryVisibility.from_filters(scope=None, project=normalized)
        )
        for _ in range(3):
            generation = await self._repo.get_memory_generation(user_id)
            memories = await self._repo.list_active_for_profile(
                user_id,
                visibility=visibility,
                static_limit=self._limits.profile_static_max_items,
                dynamic_limit=self._limits.profile_dynamic_max_items,
                dynamic_since=datetime.now(UTC)
                - timedelta(days=self._limits.profile_dynamic_window_days),
                static_min_importance=self._limits.profile_static_min_importance,
            )
            selected = select_profile_slices(memories, limits=self._limits, now=datetime.now(UTC))
            try:
                row = await self._repo.upsert_profile(
                    user_id,
                    project=normalized,
                    static_items=[item.as_dict() for item in selected.static],
                    # The dynamic slice is assembled live at read time from
                    # recall usage; persisting it would freeze a snapshot that
                    # every subsequent recall invalidates.
                    dynamic_items=[],
                    source_memory_ids=[item.id for item in selected.static],
                    content_hash=profile_content_hash(selected.static, []),
                    expected_generation=generation,
                )
            except ProfileGenerationConflict:
                continue
            return self._profile_block_from_row(row, project=normalized, dynamic=selected.dynamic)
        raise ProfileGenerationConflict

    async def _ensure_profile(self, user_id: uuid.UUID, *, project: str | None) -> ProfileBlock:
        row = await self._repo.get_profile(user_id, project=project)
        generation = await self._repo.get_memory_generation(user_id)
        if row is None or row.generation != generation:
            return await self.rebuild_profile(user_id, project=project)
        dynamic = await self._live_dynamic_items(user_id, project=project, static_row=row)
        return self._profile_block_from_row(row, project=project, dynamic=dynamic)

    async def _live_dynamic_items(
        self,
        user_id: uuid.UUID,
        *,
        project: str | None,
        static_row: Any,
    ) -> list[ProfileItem]:
        """Assemble the dynamic slice from live recall usage at read time.

        The materialized row holds only static items; recent ``recall`` hits
        must reach the profile without forcing a rebuild, so the dynamic
        candidates are selected here against the live ``last_recalled_at``.
        """
        visibility = (
            MemoryVisibility.global_only()
            if project is None
            else MemoryVisibility.from_filters(scope=None, project=project)
        )
        candidates = await self._repo.list_active_for_profile(
            user_id,
            visibility=visibility,
            static_limit=0,
            dynamic_limit=self._limits.profile_dynamic_max_items,
            dynamic_since=datetime.now(UTC)
            - timedelta(days=self._limits.profile_dynamic_window_days),
            static_min_importance=self._limits.profile_static_min_importance,
        )
        static_ids = {item.id for item in items_from_stored(static_row.static_items)}
        return select_dynamic_slice(
            candidates,
            limits=self._limits,
            now=datetime.now(UTC),
            exclude_ids=static_ids,
        )

    def _profile_block_from_row(
        self, row: Any, *, project: str | None, dynamic: Sequence[ProfileItem]
    ) -> ProfileBlock:
        static = items_from_stored(row.static_items)
        # Integrity covers the slices actually served, not just the persisted
        # static row; ``built_at`` stays the static materialization instant.
        digest = profile_content_hash(static, dynamic)
        return ProfileBlock(
            available=True,
            project=project,
            static=static,
            dynamic=list(dynamic),
            source_memory_ids=[item.id for item in (*static, *dynamic)],
            digest=digest,
            built_at=row.built_at,
        )

    async def _rebuild_profiles_for_memory(self, user_id: uuid.UUID, memory: Memory) -> None:
        """Best-effort eager rebuild of keys this memory can affect."""
        if memory.scope == "project" and memory.project:
            keys: list[str | None] = [memory.project]
        else:
            try:
                keys = [None, *(await self._repo.list_profile_projects(user_id))]
            except Exception:
                logger.warning("could not list project profiles after mutation", exc_info=True)
                keys = [None]
        await self._rebuild_profiles_for_keys(user_id, keys)

    async def _rebuild_profiles_for_keys(
        self, user_id: uuid.UUID, keys: Sequence[str | None]
    ) -> None:
        """Best-effort rebuild of explicit profile keys after a mutation."""
        for key in keys:
            try:
                await self.rebuild_profile(user_id, project=key)
            except Exception:
                logger.warning(
                    "profile rebuild failed after memory mutation; write kept",
                    exc_info=True,
                )

    def _stale_cutoff(self) -> datetime:
        """The instant before which an unconfirmed memory counts as stale."""
        return datetime.now(UTC) - timedelta(days=self._limits.stale_after_days)

    def _clamp_limit(self, requested: int | None, default: int, maximum: int) -> int:
        if requested is None:
            return default
        if not isinstance(requested, int) or isinstance(requested, bool):
            raise MemoryValidationError("limit must be an integer")
        return max(1, min(requested, maximum))

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
            raise MemoryValidationError(f"metadata exceeds {self._limits.max_metadata_keys} keys")
        for key, value in metadata.items():
            if not isinstance(key, str) or not key:
                raise MemoryValidationError("metadata keys must be non-empty strings")
            if not isinstance(value, (str, int, float, bool)) and value is not None:
                raise MemoryValidationError(f"metadata value for '{key}' must be a JSON primitive")
        serialized = json.dumps(metadata, ensure_ascii=True, sort_keys=True)
        if len(serialized.encode("utf-8")) > self._limits.max_metadata_bytes:
            raise MemoryValidationError(f"metadata exceeds {self._limits.max_metadata_bytes} bytes")
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
        reconfirmed_at=memory.reconfirmed_at,
        last_recalled_at=memory.last_recalled_at,
        recall_count=memory.recall_count,
        context_count=memory.context_count,
    )
