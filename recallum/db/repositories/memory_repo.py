"""PostgreSQL repository for memories: create, fetch, list, search, soft-delete."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import cast, func, literal, select, update
from sqlalchemy.dialects.postgresql import REGCONFIG

from recallum.db.models import Memory
from recallum.db.session import SessionProvider
from recallum.memory import MemoryVisibility

# Candidate pool cap for each retrieval signal before Reciprocal Rank Fusion.
MAX_CANDIDATES = 60


@dataclass(slots=True)
class ScoredMemory:
    """A memory row plus a per-signal score (cosine similarity or text rank)."""

    memory: Memory
    score: float


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
                importance=importance,
                source_client=source_client,
                metadata_=metadata,
            )
            session.add(memory)
            await session.flush()
            await session.refresh(memory)
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
            stmt = select(Memory).where(
                Memory.id == memory_id,
                Memory.user_id == user_id,
                Memory.deleted_at.is_(None),
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
                .where(*filters)
                .order_by(Memory.created_at.desc(), Memory.id)
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return rows, total

    async def search_vector(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        """Nearest neighbours by cosine similarity (1 - distance)."""
        async with self._sessions.for_user(user_id) as session:
            distance = Memory.embedding.cosine_distance(embedding)
            score = (literal(1.0) - distance).label("score")
            stmt = (
                select(Memory, score)
                .where(*self._filters(user_id, visibility=visibility, category=category))
                .order_by(distance)
                .limit(min(limit, MAX_CANDIDATES))
            )
            return [
                ScoredMemory(memory=row.Memory, score=float(row.score))
                for row in (await session.execute(stmt)).all()
            ]

    async def search_text(
        self,
        user_id: uuid.UUID,
        query: str,
        *,
        visibility: MemoryVisibility,
        category: str | None = None,
        limit: int,
    ) -> Sequence[ScoredMemory]:
        """Full-text candidates ranked with ts_rank_cd over the simple tsvector."""
        async with self._sessions.for_user(user_id) as session:
            ts_query = func.websearch_to_tsquery(cast("simple", REGCONFIG), query)
            rank = func.ts_rank_cd(Memory.content_tsv, ts_query).label("score")
            stmt = (
                select(Memory, rank)
                .where(
                    *self._filters(user_id, visibility=visibility, category=category),
                    Memory.content_tsv.op("@@")(ts_query),
                )
                .order_by(rank.desc(), Memory.created_at.desc())
                .limit(min(limit, MAX_CANDIDATES))
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
                .where(*self._filters(user_id, visibility=visibility, category=None))
                .order_by(Memory.importance.desc(), Memory.created_at.desc(), Memory.id)
                .limit(limit)
            )
            return (await session.execute(stmt)).scalars().all()

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
