"""PostgreSQL repository for memories: create, fetch, list, search, soft-delete."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import cast, func, literal, or_, select, text, true, update
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

from recallum.config import EMBEDDING_DIMENSIONS, TEXT_SEARCH_CONFIG
from recallum.db.models import Memory, MemoryProfile, User
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
        func.tsvector_to_array(func.to_tsvector(cast(TEXT_SEARCH_CONFIG, REGCONFIG), query))
    ).column_valued("lexeme")
    return cast(
        select(func.string_agg(func.quote_literal(lexeme), literal(" | "))).scalar_subquery(),
        TSQUERY,
    )


class BucketMismatchError(ValueError):
    """Merge sources live in different scope/project buckets.

    Raised inside the merge transaction, where the rows are actually held:
    the caller cannot pre-check without racing a concurrent write.
    """


class ProfileGenerationConflict(RuntimeError):
    """A profile rebuild raced a memory mutation and lost its CAS."""


@dataclass(slots=True)
class ScoredMemory:
    """A memory row plus a per-signal score (cosine similarity or text rank)."""

    memory: Memory
    score: float


@dataclass(frozen=True, slots=True)
class CandidatePools:
    """The ranked candidate lists a single query produced.

    Each list is ordered best-first by its own signal and the scores are not
    comparable across lists -- only the ordering is. ``vector`` is empty when
    no embedding was available; ``trigram`` is empty when the fuzzy lexical
    leg was not requested.
    """

    vector: Sequence[ScoredMemory]
    text: Sequence[ScoredMemory]
    trigram: Sequence[ScoredMemory] = ()


@dataclass(frozen=True, slots=True)
class GraphPair:
    source_id: uuid.UUID
    target_id: uuid.UUID
    similarity: float


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    memories: Sequence[Memory]
    pairs: Sequence[GraphPair]
    total: int
    model_mismatch: bool
    # Number of qualifying undirected pairs (above the similarity floor, same
    # embedding model) before the per-node neighbour cap is applied. In the
    # pairwise path this equals ``len(pairs)``; the scalable path derives the
    # same exact count from the per-node counts of a single LATERAL query.
    edge_total: int


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    """Everything ``context`` reads, from one RLS-pinned transaction.

    ``profile`` is the materialized static row (None when never built);
    ``generation`` is the user's current generation, so the caller can decide
    whether the static row is still valid. ``dynamic_candidates`` are bounded
    recently-recalled rows for read-time dynamic assembly. ``focus`` holds the
    hybrid candidate pools for the task focus, empty when no focus was given
    or the embedding service was down.
    """

    profile: MemoryProfile | None
    generation: int
    global_top: Sequence[Memory]
    project_top: Sequence[Memory]
    dynamic_candidates: Sequence[Memory]
    total_available: int
    focus: CandidatePools


def _scalable_edges_enabled(scalable_enabled: bool, total: int, scalable_min_nodes: int) -> bool:
    """Route edge computation to the bounded per-node path when either the
    explicit operator flag is set or the active node count strictly exceeds
    the activation threshold."""
    return scalable_enabled or total > scalable_min_nodes


def _cap_pairs_by_degree(pairs: Sequence[GraphPair], max_neighbours: int) -> list[GraphPair]:
    """Greedily keep the strongest pairs under the per-node neighbour cap.

    ``pairs`` are sorted by descending similarity with canonical ids as the
    stable tie-break, so the strongest edges win when a node is over its cap;
    a pair is dropped once either endpoint has reached ``max_neighbours``.
    The fake repository reuses this so both edge paths apply the same cap.
    """
    ordered = sorted(
        pairs,
        key=lambda pair: (-pair.similarity, str(pair.source_id), str(pair.target_id)),
    )
    degree: dict[uuid.UUID, int] = {}
    capped: list[GraphPair] = []
    for pair in ordered:
        if (
            degree.get(pair.source_id, 0) >= max_neighbours
            or degree.get(pair.target_id, 0) >= max_neighbours
        ):
            continue
        capped.append(pair)
        degree[pair.source_id] = degree.get(pair.source_id, 0) + 1
        degree[pair.target_id] = degree.get(pair.target_id, 0) + 1
    return capped


async def _scalable_graph_edges(
    session: AsyncSession,
    *,
    selected_ids: Sequence[uuid.UUID],
    user_id: uuid.UUID,
    min_similarity: float,
    max_neighbours: int,
) -> tuple[list[GraphPair], int]:
    """Per-node bounded kNN edges over the selected subset, in one LATERAL query.

    Each node's LATERAL returns its ``max_neighbours`` strongest qualifying
    neighbours (``right.id != left.id`` -- the kNN must consider every other
    node, not only higher ids) plus, via ``COUNT(*) OVER ()``, how many
    qualifying neighbours that node has in total. The pre-cap pair count is
    exact: cosine distance and model equality are symmetric, so every
    qualifying undirected pair is counted from both endpoints and the halved
    sum of each node's count (once per node) is the pre-cap qualifying pair
    count.

    The per-node ``LIMIT`` keeps the returned rows bounded even in a dense
    component; the exact count costs evaluating the qualifying pairs
    themselves, folded into this single statement instead of a second full
    pairwise join. Rows are canonicalised to undirected pairs and deduped (a
    pair can be emitted from both endpoints' top-k), then greedily capped per
    node so the snapshot itself stays bounded -- not only the service-layer
    greedy cap.
    """
    left = aliased(Memory, name="graph_left")
    right = aliased(Memory, name="graph_right")
    distance = left.embedding.cosine_distance(right.embedding)
    score = (literal(1.0) - distance).label("similarity")
    neighbours = (
        select(
            right.id.label("target_id"),
            score,
            func.count().over().label("node_count"),
        )
        .where(
            right.id.in_(selected_ids),
            right.id != left.id,
            right.user_id == user_id,
            right.embedding_model.is_not(None),
            left.embedding_model == right.embedding_model,
            distance <= (1.0 - min_similarity),
        )
        .order_by(score.desc(), right.id)
        .limit(max_neighbours)
        .lateral("graph_neighbours")
    )
    stmt = (
        select(
            left.id.label("source_id"),
            neighbours.c.target_id,
            neighbours.c.similarity,
            neighbours.c.node_count,
        )
        .select_from(left)
        .join(neighbours, true())
        .where(
            left.id.in_(selected_ids),
            left.user_id == user_id,
            left.embedding_model.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).all()
    # ``node_count`` is the same for every row of one node's top-k, so each
    # source node's count is taken once; every qualifying undirected pair is
    # then counted from both endpoints, making the halved sum exact.
    node_counts: dict[uuid.UUID, int] = {}
    for row in rows:
        node_counts.setdefault(row.source_id, int(row.node_count))
    edge_total = sum(node_counts.values()) // 2
    pairs: list[GraphPair] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for row in rows:
        source_id, target_id = sorted((row.source_id, row.target_id), key=str)
        if (source_id, target_id) in seen:
            continue
        seen.add((source_id, target_id))
        pairs.append(GraphPair(source_id, target_id, float(row.similarity)))
    return _cap_pairs_by_degree(pairs, max_neighbours), edge_total


class MemoryRepository:
    """All statements run inside per-user sessions with RLS context set."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    @staticmethod
    async def _increment_generation(session: AsyncSession, user_id: uuid.UUID) -> None:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(memory_generation=User.memory_generation + 1)
        )

    async def count_active(self, user_id: uuid.UUID) -> int:
        """Count active rows inside exactly one user's forced-RLS context."""
        async with self._sessions.for_user(user_id) as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(Memory)
                    .where(Memory.user_id == user_id, Memory.deleted_at.is_(None))
                )
            ).scalar_one()

    async def history(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Sequence[Memory] | None:
        """Return every ancestor oldest-first, or None when the anchor is invisible.

        Supersession became many-to-one with ``merge_memories``: several
        retired rows may point at one replacement, so ancestry is a tree,
        walked level by level and flattened by age. A linear ``update`` chain
        comes out in exactly the order it always did. The seen-set makes the
        walk bounded regardless of data (cycles are structurally impossible
        -- a replacement is always a freshly inserted row -- but an infinite
        loop is not a graceful way to learn otherwise).
        """
        async with self._sessions.for_user(user_id) as session:
            anchor = (
                await session.execute(
                    select(Memory.id).where(
                        Memory.id == memory_id,
                        Memory.user_id == user_id,
                    )
                )
            ).scalar_one_or_none()
            if anchor is None:
                return None
            ancestors: dict[uuid.UUID, Memory] = {}
            frontier: list[uuid.UUID] = [memory_id]
            while frontier:
                rows = (
                    (
                        await session.execute(
                            select(Memory)
                            .options(*_light())
                            .where(
                                Memory.user_id == user_id,
                                Memory.superseded_by.in_(frontier),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                frontier = [row.id for row in rows if row.id not in ancestors]
                for row in rows:
                    ancestors.setdefault(row.id, row)
            return sorted(ancestors.values(), key=lambda m: (m.created_at, str(m.id)))

    async def statistics(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Derive per-user aggregates in one forced-RLS transaction."""
        async with self._sessions.for_user(user_id) as session:
            rows = (
                await session.execute(
                    select(
                        Memory.category,
                        Memory.scope,
                        Memory.project,
                        Memory.importance,
                        Memory.created_at,
                        Memory.content,
                        Memory.deleted_at,
                        Memory.superseded_by,
                    ).where(Memory.user_id == user_id)
                )
            ).all()
        active = [row for row in rows if row.deleted_at is None]

        def counts(values: Sequence[Any]) -> dict[str, int]:
            result: dict[str, int] = {}
            for value in values:
                key = str(value) if value is not None else "none"
                result[key] = result.get(key, 0) + 1
            return result

        return {
            "active": len(active),
            "superseded": sum(row.superseded_by is not None for row in rows),
            "retired": sum(
                row.deleted_at is not None and row.superseded_by is None for row in rows
            ),
            "by_category": counts([row.category for row in active]),
            "by_scope": counts([row.scope for row in active]),
            "by_project": counts([row.project for row in active]),
            "by_importance": counts([row.importance for row in active]),
            "created_by_day": counts([row.created_at.date().isoformat() for row in rows]),
            "volume_bytes": sum(
                len(row.content.encode("utf-8")) + EMBEDDING_DIMENSIONS * 4 for row in rows
            ),
        }

    async def has_model_mismatch(self, user_id: uuid.UUID, model: str) -> bool:
        """Probe provenance without selecting memory content."""
        async with self._sessions.for_user(user_id) as session:
            return (
                await session.execute(
                    select(
                        select(Memory.id)
                        .where(
                            Memory.user_id == user_id,
                            Memory.deleted_at.is_(None),
                            Memory.embedding_model.is_not(None),
                            Memory.embedding_model != model,
                        )
                        .exists()
                    )
                )
            ).scalar_one()

    async def page_active_counts(
        self, *, limit: int, offset: int
    ) -> tuple[list[tuple[uuid.UUID, int]], int]:
        """Page zero-inclusive active memory counts without selecting content."""
        async with self._sessions.admin() as session:
            total = (await session.execute(select(func.count()).select_from(User))).scalar_one()
            rows = (
                await session.execute(
                    select(User.id, User.active_memory_count)
                    .order_by(User.created_at, User.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [(row.id, int(row.active_memory_count)) for row in rows], int(total)

    async def has_any_model_mismatch(self, model: str) -> bool:
        """Global existential mismatch probe; never selects memory content."""
        async with self._sessions.admin() as session:
            return (
                await session.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM memory_embedding_models
                            WHERE embedding_model IS DISTINCT FROM :model
                              AND active_count > 0
                        )
                        """
                    ),
                    {"model": model},
                )
            ).scalar_one()

    async def stale_embeddings_batch(
        self,
        user_id: uuid.UUID,
        *,
        model: str,
        after: uuid.UUID | None,
        limit: int,
    ) -> Sequence[Memory]:
        """A page of active rows whose vector provenance is NULL or another model.

        These are the rows the vector search leg cannot trust; re-embedding
        them under ``model`` restores their vector reach. Keyset-paginated by
        id so a caller that cannot fix a row (its embedding keeps failing)
        still advances past it instead of refetching it forever.
        """
        async with self._sessions.for_user(user_id) as session:
            filters: list[Any] = [
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
                or_(
                    Memory.embedding_model.is_(None),
                    Memory.embedding_model != model,
                ),
            ]
            if after is not None:
                filters.append(Memory.id > after)
            stmt = (
                select(Memory).options(*_light()).where(*filters).order_by(Memory.id).limit(limit)
            )
            return (await session.execute(stmt)).scalars().all()

    async def replace_embedding(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        embedding: list[float],
        model: str,
    ) -> bool:
        """Swap an active row's vector and provenance in place.

        Content, hash and id are untouched: the claim itself is unchanged, so
        this is maintenance of the row, not supersession. Returns ``False``
        for unknown, foreign and retired ids alike.
        """
        async with self._sessions.for_user(user_id) as session:
            result = await session.execute(
                update(Memory)
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
                .values(embedding=embedding, embedding_model=model)
            )
            return result.rowcount == 1

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
        memory_id: uuid.UUID | None = None,
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
            if memory_id is not None:
                memory.id = memory_id
            session.add(memory)
            await session.flush()
            await self._increment_generation(session, user_id)
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
        stale_before: datetime | None = None,
        fresh_since: datetime | None = None,
    ) -> tuple[Sequence[Memory], int]:
        """Return a page of active memories plus the total matching count.

        ``stale_before`` keeps only rows whose last confirmation --
        ``reconfirmed_at``, else ``created_at`` -- predates the cutoff (the
        verification queue); ``fresh_since`` is its complement. At most one
        is set; the total honours the same filter as the page.
        """
        async with self._sessions.for_user(user_id) as session:
            filters = self._filters(user_id, visibility=visibility, category=category)
            confirmed_at = func.coalesce(Memory.reconfirmed_at, Memory.created_at)
            if stale_before is not None:
                filters.append(confirmed_at < stale_before)
            if fresh_since is not None:
                filters.append(confirmed_at >= fresh_since)
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

    async def graph_snapshot(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None,
        limit: int,
        min_similarity: float,
        max_neighbours: int = 4,
        scalable_enabled: bool = False,
        scalable_min_nodes: int = 2000,
    ) -> GraphSnapshot:
        """Select bounded active nodes and comparable semantic pairs under RLS.

        Edges are computed by a pairwise self-join by default. When
        ``scalable_enabled`` is set or the active node count strictly exceeds
        ``scalable_min_nodes``, a single bounded per-node kNN LATERAL query
        over the selected subset is used instead; the pre-cap qualifying pair
        count is still reported exactly by both paths.
        """
        async with self._sessions.for_user(user_id) as session:
            filters = self._filters(user_id, visibility=visibility, category=category)
            total = (
                await session.execute(select(func.count()).select_from(Memory).where(*filters))
            ).scalar_one()
            stmt = (
                select(Memory)
                .options(*_light())
                .where(*filters)
                .order_by(Memory.importance.desc(), Memory.created_at.desc(), Memory.id)
                .limit(limit)
            )
            memories = (await session.execute(stmt)).scalars().all()
            models = {memory.embedding_model for memory in memories if memory.embedding_model}
            model_mismatch = any(memory.embedding_model is None for memory in memories) or (
                len(models) > 1
            )
            if len(memories) < 2:
                return GraphSnapshot(memories, [], total, model_mismatch, edge_total=0)

            selected_ids = [memory.id for memory in memories]
            if _scalable_edges_enabled(scalable_enabled, total, scalable_min_nodes):
                pairs, edge_total = await _scalable_graph_edges(
                    session,
                    selected_ids=selected_ids,
                    user_id=user_id,
                    min_similarity=min_similarity,
                    max_neighbours=max_neighbours,
                )
            else:
                left = aliased(Memory, name="graph_left")
                right = aliased(Memory, name="graph_right")
                distance = left.embedding.cosine_distance(right.embedding)
                score = (literal(1.0) - distance).label("similarity")
                pair_stmt = (
                    select(left.id.label("source_id"), right.id.label("target_id"), score)
                    .select_from(left, right)
                    .where(
                        left.id.in_(selected_ids),
                        right.id.in_(selected_ids),
                        left.id < right.id,
                        left.user_id == user_id,
                        right.user_id == user_id,
                        left.embedding_model.is_not(None),
                        right.embedding_model.is_not(None),
                        left.embedding_model == right.embedding_model,
                        distance <= (1.0 - min_similarity),
                    )
                    .order_by(score.desc(), left.id, right.id)
                )
                pairs = [
                    GraphPair(row.source_id, row.target_id, float(row.similarity))
                    for row in (await session.execute(pair_stmt)).all()
                ]
                edge_total = len(pairs)
            return GraphSnapshot(memories, pairs, total, model_mismatch, edge_total=edge_total)

    async def related_to(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        limit: int,
        min_similarity: float,
    ) -> Sequence[ScoredMemory]:
        """Return seed-centered thematic neighbours under one user's RLS."""
        async with self._sessions.for_user(user_id) as session:
            seed = aliased(Memory, name="related_seed")
            neighbour = aliased(Memory, name="related_neighbour")
            distance = seed.embedding.cosine_distance(neighbour.embedding)
            score = (literal(1.0) - distance).label("similarity")
            stmt = (
                select(neighbour, score)
                .options(
                    defer(neighbour.embedding, raiseload=True),
                    defer(neighbour.content_tsv, raiseload=True),
                )
                .where(
                    seed.id == memory_id,
                    seed.user_id == user_id,
                    seed.deleted_at.is_(None),
                    seed.embedding_model.is_not(None),
                    neighbour.user_id == user_id,
                    neighbour.deleted_at.is_(None),
                    neighbour.id != seed.id,
                    neighbour.embedding_model.is_not(None),
                    seed.embedding_model == neighbour.embedding_model,
                    distance <= (1.0 - min_similarity),
                )
                .order_by(score.desc(), neighbour.id)
                .limit(limit)
            )
            return [
                ScoredMemory(memory=row[0], score=float(row[1]))
                for row in (await session.execute(stmt)).all()
            ]

    async def search_candidates(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        embedding: list[float] | None,
        embedding_model: str | None,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
        trigram_min_word_similarity: float | None = None,
    ) -> CandidatePools:
        """Every retrieval signal for one query, in a single transaction.

        Replaces a pair of separately-opened searches. Each open cost a pool
        checkout, a BEGIN, a ``set_config`` round trip for the RLS context and a
        COMMIT, so one recall held two connections out of a pool of five --
        before authentication took its own. Sharing the transaction also means
        both signals observe exactly the same snapshot, so a concurrent write
        can no longer land between the two legs and put a row in one pool but
        not the other.

        ``embedding`` is ``None`` when the embedding service is unavailable; the
        vector pool is then empty and the caller degrades to lexical-only.
        ``embedding_model`` names the coordinate space the query vector lives
        in; only rows embedded in that space (or predating provenance
        tracking) may take part in the vector pool.
        ``trigram_min_word_similarity`` enables the fuzzy lexical pool; None
        skips its query entirely. Fusing the pools is deliberately left to
        the caller: it is pure computation over ranked lists, and pushing it
        behind this seam would force every adapter to reimplement it.
        """
        capped = min(limit, MAX_CANDIDATES)
        filters = self._filters(user_id, visibility=visibility, category=category)
        async with self._sessions.for_user(user_id) as session:
            vector: list[ScoredMemory] = []
            if embedding is not None:
                vector = await self._vector_candidates(
                    session, embedding, embedding_model, filters, capped
                )
            text_pool = await self._text_candidates(session, query, filters, capped)
            trigram: list[ScoredMemory] = []
            if trigram_min_word_similarity is not None:
                trigram = await self._trigram_candidates(
                    session, query, trigram_min_word_similarity, filters, capped
                )
            return CandidatePools(vector=vector, text=text_pool, trigram=trigram)

    async def _vector_candidates(
        self,
        session: AsyncSession,
        embedding: list[float],
        embedding_model: str | None,
        filters: list[Any],
        limit: int,
    ) -> list[ScoredMemory]:
        """Nearest neighbours by cosine similarity (1 - distance).

        Only rows whose stored provenance is ``embedding_model`` or NULL are
        ranked. Vectors from different models share no coordinate space, so
        their distances are noise -- and noise sometimes outranks genuine
        matches, which is worse than absence. Exclusion is not hiding: the
        textual pool still reaches those rows, and ``replace_embedding``
        (via ``recallum-admin reembed``) restores their vector reach. NULL
        provenance predates tracking and stays eligible, because treating
        unknown as foreign would blank the vector leg of every migrated
        corpus. The iterative scan keeps filling the limit with comparable
        rows despite the filter.
        """
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        distance = Memory.embedding.cosine_distance(embedding)
        score = (literal(1.0) - distance).label("score")
        comparable = or_(
            Memory.embedding_model.is_(None),
            Memory.embedding_model == embedding_model,
        )
        stmt = (
            select(Memory, score)
            .options(*_light())
            .where(*filters, comparable)
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

    async def _trigram_candidates(
        self,
        session: AsyncSession,
        query: str,
        min_word_similarity: float,
        filters: list[Any],
        limit: int,
    ) -> list[ScoredMemory]:
        """Fuzzy lexical candidates: language-neutral trigram word-similarity.

        Catches what the other legs miss: typos, identifier and camelCase
        fragments, and words the full-text dictionary mangles (``content_tsv``
        uses the English configuration, so Spanish content gets English
        stemming). ``word_similarity`` compares the query against its best
        matching extent of the content, so one close variant of one content
        word is enough. The ``<%`` predicate is what keeps the trigram GIN
        index usable; ranking is by closeness, recency breaking ties.
        """
        await session.execute(
            select(
                func.set_config(
                    "pg_trgm.word_similarity_threshold",
                    str(min_word_similarity),
                    True,  # transaction-local, like the hnsw knob above
                )
            )
        )
        score = func.word_similarity(query, Memory.content).label("score")
        stmt = (
            select(Memory, score)
            .options(*_light())
            .where(*filters, literal(query).op("<%")(Memory.content))
            .order_by(score.desc(), Memory.created_at.desc())
            .limit(limit)
        )
        return [
            ScoredMemory(memory=row.Memory, score=float(row.score))
            for row in (await session.execute(stmt)).all()
        ]

    async def context_snapshot(
        self,
        user_id: uuid.UUID,
        *,
        project: str | None,
        visibility: MemoryVisibility,
        category: str | None,
        top_limit: int,
        candidate_limit: int,
        query: str | None,
        embedding: list[float] | None,
        embedding_model: str | None,
        trigram_min_word_similarity: float | None,
        static_limit: int,
        dynamic_limit: int,
        dynamic_since: datetime,
        static_min_importance: int,
    ) -> ContextSnapshot:
        """Read everything ``context`` needs in one RLS-pinned transaction.

        Profile row, generation, importance tops, dynamic candidates, the
        visible total and (when ``query`` is set) the hybrid focus pools all
        observe the same snapshot, so a concurrent write cannot land between
        them. ``embedding`` is None when the embedding service failed before
        the call; the vector leg is skipped and the textual legs still run
        inside the same transaction.
        """
        global_visibility = MemoryVisibility.global_only()
        project_visibility = MemoryVisibility.project_only(project) if project is not None else None
        key = self._profile_key(project)
        capped = min(candidate_limit, MAX_CANDIDATES)
        async with self._sessions.for_user(user_id) as session:
            profile = (
                await session.execute(
                    select(MemoryProfile).where(
                        MemoryProfile.user_id == user_id,
                        MemoryProfile.project == key,
                    )
                )
            ).scalar_one_or_none()
            generation = int(
                (
                    await session.execute(select(User.memory_generation).where(User.id == user_id))
                ).scalar_one()
            )
            global_top = (
                (
                    await session.execute(
                        select(Memory)
                        .options(*_light())
                        .where(*self._filters(user_id, visibility=global_visibility, category=None))
                        .order_by(Memory.importance.desc(), Memory.created_at.desc(), Memory.id)
                        .limit(top_limit)
                    )
                )
                .scalars()
                .all()
            )
            project_top: Sequence[Memory] = []
            if project_visibility is not None:
                project_top = (
                    (
                        await session.execute(
                            select(Memory)
                            .options(*_light())
                            .where(
                                *self._filters(
                                    user_id, visibility=project_visibility, category=None
                                )
                            )
                            .order_by(Memory.importance.desc(), Memory.created_at.desc(), Memory.id)
                            .limit(top_limit)
                        )
                    )
                    .scalars()
                    .all()
                )
            # Up to ``static_limit`` recent rows may also win the static slice;
            # fetch that bounded overlap so read-time assembly can still fill
            # dynamic from lower-ranked recent rows.
            dynamic_candidates = (
                (
                    await session.execute(
                        select(Memory)
                        .options(*_light())
                        .where(
                            *self._filters(user_id, visibility=visibility, category=None),
                            Memory.last_recalled_at.is_not(None),
                            Memory.last_recalled_at >= dynamic_since,
                        )
                        .order_by(
                            Memory.last_recalled_at.desc(), Memory.created_at.desc(), Memory.id
                        )
                        .limit(dynamic_limit + static_limit)
                    )
                )
                .scalars()
                .all()
            )
            total_available = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Memory)
                        .where(*self._filters(user_id, visibility=visibility, category=None))
                    )
                ).scalar_one()
            )
            vector: list[ScoredMemory] = []
            text: list[ScoredMemory] = []
            trigram: list[ScoredMemory] = []
            if query is not None:
                focus_filters = self._filters(user_id, visibility=visibility, category=category)
                if embedding is not None:
                    vector = await self._vector_candidates(
                        session, embedding, embedding_model, focus_filters, capped
                    )
                text = await self._text_candidates(session, query, focus_filters, capped)
                if trigram_min_word_similarity is not None:
                    trigram = await self._trigram_candidates(
                        session, query, trigram_min_word_similarity, focus_filters, capped
                    )
            return ContextSnapshot(
                profile=profile,
                generation=generation,
                global_top=global_top,
                project_top=project_top,
                dynamic_candidates=dynamic_candidates,
                total_available=total_available,
                focus=CandidatePools(vector=vector, text=text, trigram=trigram),
            )

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
        embedding_model: str,
        scope: str,
        project: str | None,
        min_similarity: float,
        limit: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Sequence[ScoredMemory]:
        """Active memories close enough to ``embedding`` to be about the same thing.

        Scoped to the same scope and project -- those are deliberate namespaces.
        Category is deliberately NOT filtered: it is a filing label agents get
        wrong often enough that a near-duplicate stored under another category
        is the common way contradictions accumulate unseen. Each hit carries its
        category, so a filing mismatch is visible to the caller. Similarity is
        evidence of overlap, never of contradiction -- that judgement needs to
        read the content, and is the caller's.

        Only vectors from ``embedding_model`` (or NULL provenance) are
        compared: the probe vector just came from that model, and distances
        into another model's space would report noise as subject overlap.
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
                or_(
                    Memory.embedding_model.is_(None),
                    Memory.embedding_model == embedding_model,
                ),
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
            if any(value is not None for value in (importance, category, metadata)):
                await self._increment_generation(session, user_id)
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
                metadata_=(metadata if metadata is not None else dict(original.metadata_ or {})),
            )
            session.add(replacement)
            # Retire the original first so it leaves the partial unique index
            # before the replacement lands; otherwise re-stating a memory in
            # slightly different words would collide with itself.
            original.deleted_at = func.now()
            await session.flush()
            original.superseded_by = replacement.id
            await self._increment_generation(session, user_id)
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
            if result.rowcount == 1:
                await self._increment_generation(session, user_id)
            return result.rowcount == 1

    async def merge_memories(
        self,
        user_id: uuid.UUID,
        source_ids: Sequence[uuid.UUID],
        *,
        content: str,
        content_hash: str,
        embedding: list[float],
        embedding_model: str | None,
        category: str,
        importance: int | None,
        source_client: str | None,
        metadata: dict[str, Any],
    ) -> tuple[Memory, list[uuid.UUID]] | None:
        """Retire several memories and replace them with one consolidated claim.

        All-or-nothing inside one transaction: every source must be an active
        row of this user's, and all must share one scope/project bucket
        (``BucketMismatchError`` otherwise -- merging across buckets would
        move claims between namespaces, which is ``reassign_project``'s
        supervised territory). Sources are retired *before* the replacement
        is inserted, so consolidating onto one source's exact wording never
        trips the active-duplicate index; a collision with an unrelated
        active row still raises ``IntegrityError`` and rolls everything back.
        ``importance=None`` inherits the loudest source. Unknown, foreign and
        already-retired ids are indistinguishable: ``None``, nothing changed.
        """
        unique_ids = list(dict.fromkeys(source_ids))
        async with self._sessions.for_user(user_id) as session:
            rows = (
                (
                    await session.execute(
                        select(Memory)
                        .options(*_light())
                        .where(
                            Memory.user_id == user_id,
                            Memory.id.in_(unique_ids),
                            Memory.deleted_at.is_(None),
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(unique_ids):
                return None
            if len({(row.scope, row.project or "") for row in rows}) != 1:
                raise BucketMismatchError("sources span different scopes or projects")
            await session.execute(
                update(Memory)
                .where(Memory.user_id == user_id, Memory.id.in_(unique_ids))
                .values(deleted_at=func.now())
            )
            replacement = Memory(
                user_id=user_id,
                scope=rows[0].scope,
                project=rows[0].project,
                category=category,
                content=content,
                content_hash=content_hash,
                embedding=embedding,
                embedding_model=embedding_model,
                importance=(
                    importance if importance is not None else max(row.importance for row in rows)
                ),
                source_client=source_client,
                metadata_=metadata,
            )
            session.add(replacement)
            await session.flush()
            await session.execute(
                update(Memory)
                .where(Memory.user_id == user_id, Memory.id.in_(unique_ids))
                .values(superseded_by=replacement.id)
            )
            await self._increment_generation(session, user_id)
            await session.refresh(replacement, attribute_names=["created_at"])
            return replacement, [row.id for row in rows]

    async def mark_reconfirmed(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> Memory | None:
        """Stamp ``reconfirmed_at`` on an active memory and return the fresh row.

        Called when identical content is re-stored: the claim was just observed
        to still hold, which is a freshness signal, not a new claim. Returns
        ``None`` for unknown, foreign or retired ids.
        """
        async with self._sessions.for_user(user_id) as session:
            result = await session.execute(
                update(Memory)
                .where(
                    Memory.id == memory_id,
                    Memory.user_id == user_id,
                    Memory.deleted_at.is_(None),
                )
                .values(reconfirmed_at=func.now())
            )
            if result.rowcount != 1:
                return None
            await self._increment_generation(session, user_id)
            return (
                await session.execute(
                    select(Memory)
                    .options(*_light())
                    .where(Memory.id == memory_id, Memory.user_id == user_id)
                )
            ).scalar_one_or_none()

    async def mark_recalled(self, user_id: uuid.UUID, memory_ids: Sequence[uuid.UUID]) -> None:
        """Record that these memories matched a ``recall`` query.

        Recall hits only: ``context`` snapshot serves go through
        ``mark_seen_in_context``, because snapshots select by importance and
        folding their serves in here would turn ``recall_count`` -- the
        signal ``recall_usage_weight`` is waiting on -- into an importance
        echo. One bounded UPDATE, outside the read that produced the ids.
        Callers treat failure as loggable noise: usage is a signal, never a
        dependency of the read path.

        Deliberately does NOT bump ``memory_generation``: usage is not a
        corpus or static-eligibility mutation, so a recall must never force
        the next ``context`` to rebuild the materialized profile.
        """
        if not memory_ids:
            return
        async with self._sessions.for_user(user_id) as session:
            await session.execute(
                update(Memory)
                .where(
                    Memory.user_id == user_id,
                    Memory.id.in_(list(memory_ids)),
                    Memory.deleted_at.is_(None),
                )
                .values(
                    recall_count=Memory.recall_count + 1,
                    last_recalled_at=func.now(),
                )
            )

    async def mark_seen_in_context(
        self, user_id: uuid.UUID, memory_ids: Sequence[uuid.UUID]
    ) -> None:
        """Record that these memories rode along in a ``context`` snapshot.

        Same failure contract as ``mark_recalled``; deliberately a separate
        counter so snapshot exposure never masquerades as query relevance.
        """
        if not memory_ids:
            return
        async with self._sessions.for_user(user_id) as session:
            await session.execute(
                update(Memory)
                .where(
                    Memory.user_id == user_id,
                    Memory.id.in_(list(memory_ids)),
                    Memory.deleted_at.is_(None),
                )
                .values(context_count=Memory.context_count + 1)
            )

    async def count_active_visible(
        self, user_id: uuid.UUID, *, visibility: MemoryVisibility
    ) -> int:
        """Count active rows under a visibility filter (context transparency)."""
        async with self._sessions.for_user(user_id) as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(Memory)
                    .where(*self._filters(user_id, visibility=visibility, category=None))
                )
            ).scalar_one()

    async def reassign_project(
        self,
        user_id: uuid.UUID,
        *,
        from_project: str,
        to_project: str,
    ) -> tuple[int, list[uuid.UUID]]:
        """Move every active memory from one project key to another.

        A key migration, not an edit: content, embeddings and scope are
        untouched, so no re-embedding is needed. Rows whose content already
        exists active under the target key are left in place and reported --
        moving them would break the dedup key, and choosing which duplicate
        survives is the owner's call, not this method's. Both statements share
        one transaction so the conflict list matches what was actually skipped.
        """
        async with self._sessions.for_user(user_id) as session:
            target_hashes = select(Memory.content_hash).where(
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
                Memory.scope == "project",
                Memory.project == to_project,
            )
            source_filters = [
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
                Memory.scope == "project",
                Memory.project == from_project,
            ]
            conflicts = list(
                (
                    await session.execute(
                        select(Memory.id)
                        .where(*source_filters, Memory.content_hash.in_(target_hashes))
                        .order_by(Memory.created_at.desc(), Memory.id)
                    )
                ).scalars()
            )
            moved = await session.execute(
                update(Memory)
                .where(*source_filters, Memory.content_hash.not_in(target_hashes))
                .values(project=to_project)
            )
            if moved.rowcount:
                await self._increment_generation(session, user_id)
            return int(moved.rowcount or 0), conflicts

    # ------------------------------------------------------------------
    # materialized profiles
    # ------------------------------------------------------------------

    @staticmethod
    def _profile_key(project: str | None) -> str:
        """Empty string is the user-global profile key in storage."""
        return project or ""

    async def get_profile(
        self, user_id: uuid.UUID, *, project: str | None = None
    ) -> MemoryProfile | None:
        """Return the materialized profile for a key, or None if missing."""
        key = self._profile_key(project)
        async with self._sessions.for_user(user_id) as session:
            return (
                await session.execute(
                    select(MemoryProfile).where(
                        MemoryProfile.user_id == user_id,
                        MemoryProfile.project == key,
                    )
                )
            ).scalar_one_or_none()

    async def get_memory_generation(self, user_id: uuid.UUID) -> int:
        async with self._sessions.for_user(user_id) as session:
            value = (
                await session.execute(select(User.memory_generation).where(User.id == user_id))
            ).scalar_one()
            return int(value)

    async def list_profile_projects(self, user_id: uuid.UUID) -> Sequence[str]:
        """Return existing non-global profile keys for eager global rebuilds."""
        async with self._sessions.for_user(user_id) as session:
            rows = await session.execute(
                select(MemoryProfile.project)
                .where(MemoryProfile.user_id == user_id, MemoryProfile.project != "")
                .order_by(MemoryProfile.project)
            )
            return rows.scalars().all()

    async def upsert_profile(
        self,
        user_id: uuid.UUID,
        *,
        project: str | None,
        static_items: list[dict[str, Any]],
        dynamic_items: list[dict[str, Any]],
        source_memory_ids: Sequence[uuid.UUID],
        content_hash: str,
        expected_generation: int,
    ) -> MemoryProfile:
        """Insert or replace only if the source generation is still current."""
        key = self._profile_key(project)
        ids = list(source_memory_ids)
        async with self._sessions.for_user(user_id) as session:
            current = (
                await session.execute(
                    select(User.memory_generation).where(User.id == user_id).with_for_update()
                )
            ).scalar_one()
            if int(current) != expected_generation:
                raise ProfileGenerationConflict
            stmt = (
                pg_insert(MemoryProfile)
                .values(
                    user_id=user_id,
                    project=key,
                    static_items=static_items,
                    dynamic_items=dynamic_items,
                    source_memory_ids=ids,
                    content_hash=content_hash,
                    generation=expected_generation,
                    built_at=func.now(),
                )
                .on_conflict_do_update(
                    index_elements=[MemoryProfile.user_id, MemoryProfile.project],
                    set_={
                        "static_items": static_items,
                        "dynamic_items": dynamic_items,
                        "source_memory_ids": ids,
                        "content_hash": content_hash,
                        "generation": expected_generation,
                        "built_at": func.now(),
                    },
                )
                .returning(MemoryProfile)
            )
            row = (await session.execute(stmt)).scalar_one()
            await session.refresh(row, attribute_names=["built_at"])
            return row

    async def list_active_for_profile(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        static_limit: int,
        dynamic_limit: int,
        dynamic_since: datetime,
        static_min_importance: int = 8,
    ) -> Sequence[Memory]:
        """Fetch bounded static and recent-dynamic candidates in their own orders."""
        async with self._sessions.for_user(user_id) as session:
            filters = self._filters(user_id, visibility=visibility, category=None)
            static_stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    *filters,
                    (Memory.category.in_(("preference", "constraint")))
                    | (Memory.importance >= static_min_importance),
                )
                .order_by(
                    Memory.importance.desc(),
                    func.coalesce(Memory.reconfirmed_at, Memory.created_at).desc(),
                    Memory.id,
                )
                .limit(static_limit)
            )
            dynamic_stmt = (
                select(Memory)
                .options(*_light())
                .where(
                    *filters,
                    Memory.last_recalled_at.is_not(None),
                    Memory.last_recalled_at >= dynamic_since,
                )
                .order_by(Memory.last_recalled_at.desc(), Memory.created_at.desc(), Memory.id)
                # Up to ``static_limit`` recent rows may also win the static
                # slice. Fetch that bounded overlap so selection can still fill
                # dynamic from lower-ranked recent rows.
                .limit(dynamic_limit + static_limit)
            )
            static = (await session.execute(static_stmt)).scalars().all()
            dynamic = (await session.execute(dynamic_stmt)).scalars().all()
            unique: dict[uuid.UUID, Memory] = {}
            for memory in (*static, *dynamic):
                unique.setdefault(memory.id, memory)
            return list(unique.values())

    def _visibility_filters(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        active_only: bool,
    ) -> list[Any]:
        filters: list[Any] = [Memory.user_id == user_id]
        if active_only:
            filters.append(Memory.deleted_at.is_(None))
        if visibility.mode == "global":
            filters.append(Memory.scope == "global")
        elif visibility.mode == "project":
            filters.append(Memory.scope == "project")
            filters.append(Memory.project == visibility.project)
        elif visibility.mode == "global_and_project":
            filters.append(
                or_(
                    Memory.scope == "global",
                    (Memory.scope == "project") & (Memory.project == visibility.project),
                )
            )
        return filters

    def _filters(
        self,
        user_id: uuid.UUID,
        *,
        visibility: MemoryVisibility,
        category: str | None,
    ) -> list[Any]:
        """Translate domain visibility into PostgreSQL adapter expressions."""
        filters = self._visibility_filters(user_id, visibility=visibility, active_only=True)
        if category is not None:
            filters.append(Memory.category == category)
        return filters
