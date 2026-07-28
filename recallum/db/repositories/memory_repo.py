"""PostgreSQL repository for memories: create, fetch, list, search, soft-delete."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import cast, func, literal, select, text, update
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from recallum.config import TEXT_SEARCH_CONFIG
from recallum.db.models import Memory
from recallum.db.session import SessionProvider
from recallum.memory import MemoryVisibility

# Candidate pool cap for each retrieval signal before Reciprocal Rank Fusion.
MAX_CANDIDATES = 60


def _light() -> tuple[Any, ...]:
    """Loader options that skip the two columns no caller ever reads.

    ``embedding`` is 768 float4 (~3 KB per row) and ``content_tsv`` is the full
    lexeme vector; a single ``recall`` fetches up to 120 candidate rows, so
    leaving them in costs roughly 360 KB on the wire and ~92k throwaway floats
    per call. ``raiseload=True`` makes a later attribute access fail loudly
    instead of emitting lazy IO from async code, where it would surface as an
    opaque greenlet error.
    """
    return (
        defer(Memory.embedding, raiseload=True),
        defer(Memory.content_tsv, raiseload=True),
    )


def _or_tsquery(query: str) -> Any:
    """Build an OR tsquery whose lexemes are normalised exactly like the column.

    ``websearch_to_tsquery`` ANDs every term, which makes conversational
    queries match nothing. Running the raw query through ``to_tsvector`` with
    the same configuration as ``content_tsv`` applies the same stopword removal
    and stemming, and re-joining the resulting lexemes with ``|`` turns "all
    terms required" into "any term counts". ``ts_rank_cd`` then supplies the
    gradient: a row covering three query lexemes outranks one covering a single
    lexeme, so recall improves without precision collapsing.

    The lexemes are already normalised, so they are quoted and cast rather than
    passed back through ``to_tsquery``, which would stem them a second time.
    A query of nothing but stopwords yields SQL NULL, and ``tsv @@ NULL`` is
    NULL, so such a query matches no rows instead of raising.
    """
    lexeme = func.unnest(
        func.tsvector_to_array(
            func.to_tsvector(cast(TEXT_SEARCH_CONFIG, REGCONFIG), query)
        )
    ).column_valued("lexeme")
    return cast(
        select(func.string_agg(func.quote_literal(lexeme), literal(" | "))).scalar_subquery(),
        TSQUERY,
    )


@dataclass(slots=True)
class ScoredMemory:
    """A memory row plus a per-signal score (cosine similarity or text rank)."""

    memory: Memory
    score: float


@dataclass(frozen=True, slots=True)
class CandidatePools:
    """The two ranked candidate lists a single query produced.

    Each list is ordered best-first by its own signal and the scores are not
    comparable across lists -- only the ordering is. ``vector`` is empty when no
    embedding was available.
    """

    vector: Sequence[ScoredMemory]
    text: Sequence[ScoredMemory]


class MemoryRepository:
    """All statements run inside per-user sessions with RLS context set."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_memory(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        project: str | None,
        category: str,
        content: str,
        content_hash: str,
        embedding: list[float],
        embedding_model: str | None,
        importance: int,
        source_client: str | None,
        metadata: dict[str, Any],
    ) -> Memory:
        """Insert a memory. Raises IntegrityError on exact active duplicate."""
        async with self._sessions.for_user(user_id) as session:
            memory = Memory(
                user_id=user_id,
                scope=scope,
                project=project,
                category=category,
                content=content,
                content_hash=content_hash,
                embedding=embedding,
                embedding_model=embedding_model,
                importance=importance,
                source_client=source_client,
                metadata_=metadata,
            )
            session.add(memory)
            await session.flush()
            # Only ``created_at`` is server-generated and actually read back.
            # A bare refresh() would re-select the 768-dimension vector that
            # was just written, plus the generated tsvector nobody reads.
            await session.refresh(memory, attribute_names=["created_at"])
            return memory

    async def find_active_by_hash(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        project: str | None,
        content_hash: str,
    ) -> Memory | None:
        """Return the active memory matching the dedup key, if any."""
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    Memory.user_id == user_id,
                    Memory.scope == scope,
                    func.coalesce(Memory.project, "") == (project or ""),
                    Memory.content_hash == content_hash,
                    Memory.deleted_at.is_(None),
                )
                .limit(1)
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_active(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def list_active(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
        offset: int = 0,
    ) -> tuple[Sequence[Memory], int]:
        """Return a page of active memories plus the total matching count."""
        async with self._sessions.for_user(user_id) as session:
            filters = self._filters(user_id, visibility=visibility, category=category)
            count_stmt = select(func.count()).select_from(Memory).where(*filters)
            total = (await session.execute(count_stmt)).scalar_one()
            stmt = (
                select(Memory)
                .options(*_light())
                .where(*filters)
                .order_by(Memory.created_at.desc(), Memory.id)
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return rows, total

    async def search_candidates(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        embedding: list[float] | None,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> CandidatePools:
        """Both retrieval signals for one query, in a single transaction.

        Replaces a pair of separately-opened searches. Each open cost a pool
        checkout, a BEGIN, a ``set_config`` round trip for the RLS context and a
        COMMIT, so one recall held two connections out of a pool of five --
        before authentication took its own. Sharing the transaction also means
        both signals observe exactly the same snapshot, so a concurrent write
        can no longer land between the two legs and put a row in one pool but
        not the other.

        ``embedding`` is ``None`` when the embedding service is unavailable; the
        vector pool is then empty and the caller degrades to textual only.
        Fusing the two pools is deliberately left to the caller: it is pure
        computation over ranked lists, and pushing it behind this seam would
        force every adapter to reimplement it.
        """
        capped = min(limit, MAX_CANDIDATES)
        filters = self._filters(user_id, visibility=visibility, category=category)
        async with self._sessions.for_user(user_id) as session:
            vector: list[ScoredMemory] = []
            if embedding is not None:
                vector = await self._vector_candidates(session, embedding, filters, capped)
            text_pool = await self._text_candidates(session, query, filters, capped)
            return CandidatePools(vector=vector, text=text_pool)

    async def _vector_candidates(
        self,
        session: AsyncSession,
        embedding: list[float],
        filters: list[Any],
        limit: int,
    ) -> list[ScoredMemory]:
        """Nearest neighbours by cosine similarity (1 - distance)."""
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        distance = Memory.embedding.cosine_distance(embedding)
        score = (literal(1.0) - distance).label("score")
        stmt = (
            select(Memory, score)
            .options(*_light())
            .where(*filters)
            .order_by(distance)
            .limit(limit)
        )
        return [
            ScoredMemory(memory=row.Memory, score=float(row.score))
            for row in (await session.execute(stmt)).all()
        ]

    async def _text_candidates(
        self,
        session: AsyncSession,
        query: str,
        filters: list[Any],
        limit: int,
    ) -> list[ScoredMemory]:
        """Full-text candidates: any query term counts, ranked by coverage.

        Matching is whole-word and case-insensitive, tolerates query terms
        absent from the content, and tolerates common inflectional differences
        between query and content. Query operators (AND, OR, negation, quoted
        phrases) are deliberately not supported: every term is a hint, never a
        requirement. ``tests/contract/memory_repository.py`` pins this, because
        it is the part of the interface a caller cannot infer from the types.
        """
        ts_query = _or_tsquery(query)
        rank = func.ts_rank_cd(Memory.content_tsv, ts_query).label("score")
        stmt = (
            select(Memory, rank)
            .options(*_light())
            .where(*filters, Memory.content_tsv.op("@@")(ts_query))
            .order_by(rank.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        return [
            ScoredMemory(memory=row.Memory, score=float(row.score))
            for row in (await session.execute(stmt)).all()
        ]

    async def most_important_active(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        limit: int,
    ) -> Sequence[Memory]:
        """Active memories ordered by importance then recency (for context)."""
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Memory)
                .options(*_light())
                .where(*self._filters(user_id, visibility=visibility, category=None))
                .order_by(Memory.importance.desc(), Memory.created_at.desc(), Memory.id)
                .limit(limit)
            )
            return (await session.execute(stmt)).scalars().all()

    async def similar_active(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        category: str,
        min_similarity: float,
        limit: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Sequence[ScoredMemory]:
        """Active memories close enough to ``embedding`` to be about the same thing.

        Scoped to the same scope, project and category, because two memories can
        only conflict if they are claims of the same kind about the same
        subject. Similarity is evidence of overlap, never of contradiction --
        that judgement needs to read the content, and is the caller's.
        """
        async with self._sessions.for_user(user_id) as session:
            await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
            distance = Memory.embedding.cosine_distance(embedding)
            score = (literal(1.0) - distance).label("score")
            filters = [
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
                Memory.scope == scope,
                func.coalesce(Memory.project, "") == (project or ""),
                Memory.category == category,
                distance <= (1.0 - min_similarity),
            ]
            if exclude_id is not None:
                filters.append(Memory.id != exclude_id)
            stmt = (
                select(Memory, score)
                .options(*_light())
                .where(*filters)
                .order_by(distance)
                .limit(limit)
            )
            return [
                ScoredMemory(memory=row.Memory, score=float(row.score))
                for row in (await session.execute(stmt)).all()
            ]

    async def update_attributes(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        importance: int | None,
        category: str | None,
        metadata: dict[str, Any] | None,
    ) -> Memory | None:
        """Change what a memory is filed under, not what it claims.

        Importance, category and metadata are bookkeeping about a fact, so they
        are edited in place and no history is kept. Content is different: it is
        the fact, and changing it goes through ``supersede``.
        """
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
                .with_for_update()
            )
            memory = (await session.execute(stmt)).scalar_one_or_none()
            if memory is None:
                return None
            if importance is not None:
                memory.importance = importance
            if category is not None:
                memory.category = category
            if metadata is not None:
                memory.metadata_ = metadata
            await session.flush()
            return memory

    async def supersede(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        content: str,
        content_hash: str,
        embedding: list[float],
        embedding_model: str | None,
        category: str | None,
        importance: int | None,
        metadata: dict[str, Any] | None,
        source_client: str | None,
    ) -> Memory | None:
        """Replace an active memory with a new one, atomically.

        Both halves -- inserting the replacement and retiring the original --
        happen in one transaction, so a crash can never leave the fact recorded
        twice or not at all. The replacement inherits the original's scope and
        project: moving a memory between projects is a different operation and
        would change the deduplication key underneath it.

        Returns ``None`` when the id is unknown or owned by someone else, which
        the caller must not distinguish. Raises ``IntegrityError`` when the new
        content already exists as a separate active memory.
        """
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
                .with_for_update()
            )
            original = (await session.execute(stmt)).scalar_one_or_none()
            if original is None:
                return None

            replacement = Memory(
                user_id=user_id,
                scope=original.scope,
                project=original.project,
                category=category if category is not None else original.category,
                content=content,
                content_hash=content_hash,
                embedding=embedding,
                embedding_model=embedding_model,
                importance=importance if importance is not None else original.importance,
                source_client=(
                    source_client if source_client is not None else original.source_client
                ),
                metadata_=(
                    metadata if metadata is not None else dict(original.metadata_ or {})
                ),
            )
            session.add(replacement)
            # Retire the original first so it leaves the partial unique index
            # before the replacement lands; otherwise re-stating a memory in
            # slightly different words would collide with itself.
            original.deleted_at = func.now()
            await session.flush()
            original.superseded_by = replacement.id
            await session.flush()
            await session.refresh(replacement, attribute_names=["created_at"])
            return replacement

    async def soft_delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> bool:
        """Logically delete a memory. Returns False when not found/foreign."""
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                update(Memory)
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
            )
            result = await session.execute(stmt)
            return result.rowcount == 1

    def _filters(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None,
    ) -> list[Any]:
        """Translate domain visibility into PostgreSQL adapter expressions."""
        filters: list[Any] = [Memory.user_id == user_id, Memory.deleted_at.is_(None)]
        if visibility.mode == "global":
            filters.append(Memory.scope == "global")
        elif visibility.mode == "project":
            filters.extend(
                (Memory.scope == "project", Memory.project == visibility.project)
            )
        elif visibility.mode == "global_and_project":
            filters.append(
                (Memory.scope == "global")
                | ((Memory.scope == "project") & (Memory.project == visibility.project))
            )
        if category is not None:
            filters.append(Memory.category == category)
        return filters
