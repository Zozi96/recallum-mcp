"""PostgreSQL repository for skills: create, fetch, match, supersede, forget."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import cast, func, literal, or_, select, text, update
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from recallum.config import TEXT_SEARCH_CONFIG
from recallum.db.models import Skill
from recallum.db.session import SessionProvider
from recallum.memory import MemoryVisibility

# Candidate pool cap for each retrieval signal before Reciprocal Rank Fusion.
MAX_CANDIDATES = 60


def _light() -> tuple[Any, ...]:
    """Loader options skipping the two columns no caller reads directly.

    Same rationale as ``memory_repo._light``: ``embedding`` and ``search_tsv``
    are never read by name, only matched against in SQL.
    """
    return (
        defer(Skill.embedding, raiseload=True),
        defer(Skill.search_tsv, raiseload=True),
    )


def _or_tsquery(query: str) -> Any:
    """Build an OR tsquery, same shape as ``memory_repo._or_tsquery``."""
    lexeme = func.unnest(
        func.tsvector_to_array(func.to_tsvector(cast(TEXT_SEARCH_CONFIG, REGCONFIG), query))
    ).column_valued("lexeme")
    return cast(
        select(func.string_agg(func.quote_literal(lexeme), literal(" | "))).scalar_subquery(),
        TSQUERY,
    )


@dataclass(slots=True)
class ScoredSkill:
    """A skill row plus a per-signal score (cosine similarity or text rank)."""

    skill: Skill
    score: float


@dataclass(frozen=True, slots=True)
class SkillCandidatePools:
    """The ranked candidate lists one ``match_skills`` query produced.

    ``vector`` is empty when no embedding was available (degraded lexical
    mode); there is no trigram leg -- ``match_skills`` is hybrid vector plus
    exact full-text only, unlike ``recall``'s three-leg fusion.
    """

    vector: Sequence[ScoredSkill]
    text: Sequence[ScoredSkill]


class SkillRepository:
    """All statements run inside per-user sessions with RLS context set."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create_skill(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        project: str | None,
        name: str,
        description: str,
        triggers: list[str],
        steps: list[str],
        constraints: str | None,
        content_hash: str,
        embedding: list[float],
        source_type: str,
        source_ref: str | None,
        version: int = 1,
    ) -> Skill:
        """Insert a skill row. Raises IntegrityError on an active name collision."""
        async with self._sessions.for_user(user_id) as session:
            skill = Skill(
                user_id=user_id,
                scope=scope,
                project=project,
                name=name,
                description=description,
                triggers=triggers,
                steps=steps,
                constraints=constraints,
                version=version,
                content_hash=content_hash,
                embedding=embedding,
                source_type=source_type,
                source_ref=source_ref,
            )
            session.add(skill)
            await session.flush()
            await session.refresh(skill, attribute_names=["created_at"])
            return skill

    async def find_active_by_name(
        self,
        user_id: uuid.UUID,
        *,
        scope: str,
        project: str | None,
        name: str,
    ) -> Skill | None:
        """Return the active skill in this (scope, project, name) bucket, if any."""
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Skill)
                .options(*_light())
                .where(
                    Skill.user_id == user_id,
                    Skill.scope == scope,
                    func.coalesce(Skill.project, "") == (project or ""),
                    Skill.name == name,
                    Skill.deleted_at.is_(None),
                )
                .limit(1)
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def get_active(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill | None:
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Skill)
                .options(*_light())
                .where(
                    Skill.id == skill_id,
                    Skill.user_id == user_id,
                    Skill.deleted_at.is_(None),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none()

    async def search_candidates(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        embedding: list[float] | None,
        visibility: MemoryVisibility,
        limit: int,
    ) -> SkillCandidatePools:
        """Every retrieval signal for one ``match_skills`` query, in one transaction.

        ``embedding`` is ``None`` when the embedding service is unavailable;
        the vector pool is then empty and the caller degrades to lexical-only.
        """
        capped = min(limit, MAX_CANDIDATES)
        filters = self._filters(user_id, visibility=visibility)
        async with self._sessions.for_user(user_id) as session:
            vector: list[ScoredSkill] = []
            if embedding is not None:
                vector = await self._vector_candidates(session, embedding, filters, capped)
            text_pool = await self._text_candidates(session, query, filters, capped)
            return SkillCandidatePools(vector=vector, text=text_pool)

    async def _vector_candidates(
        self,
        session: AsyncSession,
        embedding: list[float],
        filters: list[Any],
        limit: int,
    ) -> list[ScoredSkill]:
        """Nearest neighbours by cosine similarity (1 - distance)."""
        await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        distance = Skill.embedding.cosine_distance(embedding)
        score = (literal(1.0) - distance).label("score")
        stmt = (
            select(Skill, score).options(*_light()).where(*filters).order_by(distance).limit(limit)
        )
        return [
            ScoredSkill(skill=row.Skill, score=float(row.score))
            for row in (await session.execute(stmt)).all()
        ]

    async def _text_candidates(
        self,
        session: AsyncSession,
        query: str,
        filters: list[Any],
        limit: int,
    ) -> list[ScoredSkill]:
        """Full-text candidates: any query term counts, ranked by coverage."""
        ts_query = _or_tsquery(query)
        rank = func.ts_rank_cd(Skill.search_tsv, ts_query).label("score")
        stmt = (
            select(Skill, rank)
            .options(*_light())
            .where(*filters, Skill.search_tsv.op("@@")(ts_query))
            .order_by(rank.desc(), Skill.created_at.desc())
            .limit(limit)
        )
        return [
            ScoredSkill(skill=row.Skill, score=float(row.score))
            for row in (await session.execute(stmt)).all()
        ]

    async def similar_active(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        min_similarity: float,
        limit: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Sequence[ScoredSkill]:
        """Active skills close enough to ``embedding`` to be about the same procedure.

        Scoped to the same scope and project bucket, matching
        ``memory_repo.similar_active``.
        """
        async with self._sessions.for_user(user_id) as session:
            await session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
            distance = Skill.embedding.cosine_distance(embedding)
            score = (literal(1.0) - distance).label("score")
            filters = [
                Skill.user_id == user_id,
                Skill.deleted_at.is_(None),
                Skill.scope == scope,
                func.coalesce(Skill.project, "") == (project or ""),
                distance <= (1.0 - min_similarity),
            ]
            if exclude_id is not None:
                filters.append(Skill.id != exclude_id)
            stmt = (
                select(Skill, score)
                .options(*_light())
                .where(*filters)
                .order_by(distance)
                .limit(limit)
            )
            return [
                ScoredSkill(skill=row.Skill, score=float(row.score))
                for row in (await session.execute(stmt)).all()
            ]

    async def supersede(
        self,
        user_id: uuid.UUID,
        skill_id: uuid.UUID,
        *,
        description: str,
        triggers: list[str],
        steps: list[str],
        constraints: str | None,
        content_hash: str,
        embedding: list[float],
        source_type: str | None,
        source_ref: str | None,
        set_source_ref: bool,
    ) -> Skill | None:
        """Replace an active skill with a new version, atomically.

        The replacement inherits scope, project and name from the original
        and increments ``version``. Returns ``None`` when the id is unknown
        or owned by someone else, which the caller must not distinguish.
        """
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                select(Skill)
                .options(*_light())
                .where(
                    Skill.id == skill_id,
                    Skill.user_id == user_id,
                    Skill.deleted_at.is_(None),
                )
                .with_for_update()
            )
            original = (await session.execute(stmt)).scalar_one_or_none()
            if original is None:
                return None
            replacement = Skill(
                user_id=user_id,
                scope=original.scope,
                project=original.project,
                name=original.name,
                description=description,
                triggers=triggers,
                steps=steps,
                constraints=constraints,
                version=original.version + 1,
                content_hash=content_hash,
                embedding=embedding,
                source_type=(source_type if source_type is not None else original.source_type),
                source_ref=(source_ref if set_source_ref else original.source_ref),
            )
            session.add(replacement)
            # Retire the original first so it leaves the partial unique index
            # before the replacement lands.
            original.deleted_at = func.now()
            await session.flush()
            original.superseded_by = replacement.id
            await session.flush()
            await session.refresh(replacement, attribute_names=["created_at"])
            return replacement

    async def soft_delete(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> bool:
        """Logically delete a skill. Returns False when not found/foreign."""
        async with self._sessions.for_user(user_id) as session:
            stmt = (
                update(Skill)
                .where(
                    Skill.id == skill_id,
                    Skill.user_id == user_id,
                    Skill.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
            )
            result = await session.execute(stmt)
            return result.rowcount == 1

    def _filters(self, user_id: uuid.UUID, *, visibility: MemoryVisibility) -> list[Any]:
        """Translate domain visibility into PostgreSQL adapter expressions."""
        filters: list[Any] = [Skill.user_id == user_id, Skill.deleted_at.is_(None)]
        if visibility.mode == "global":
            filters.append(Skill.scope == "global")
        elif visibility.mode == "project":
            filters.append(Skill.scope == "project")
            filters.append(Skill.project == visibility.project)
        elif visibility.mode == "global_and_project":
            filters.append(
                or_(
                    Skill.scope == "global",
                    (Skill.scope == "project") & (Skill.project == visibility.project),
                )
            )
        return filters
