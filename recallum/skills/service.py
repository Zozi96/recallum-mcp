"""Skill service: save, match, get and forget.

Business rules implemented here:
- ``save_skill`` embeds before persisting. No active skill with that name in
  that (scope, project) bucket creates version 1. An active skill with the
  same name and identical (hashed) steps returns the existing row unchanged.
  Differing steps require ``replace=True``, which supersedes the active row
  with a new version, same shape as memory ``update``.
- ``match_skills`` fuses vector and textual candidates with the shared RRF
  and degrades to textual-only (flagged) when Ollama cannot embed the query.
- ``get_skill``/``forget_skill`` are the by-id read and logical delete;
  unknown, foreign and retired ids look identical, matching the memory tools.
- No automatic extraction: every skill is written by an explicit ``save_skill``
  call, never derived from a session or transcript by the server itself.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import uuid
from typing import get_args

from sqlalchemy.exc import IntegrityError

from recallum.boundary_types import StrictPositiveLimit
from recallum.db.repositories.skill_repo import ScoredSkill, SkillRepository
from recallum.embeddings.ollama import EmbeddingError, OllamaEmbeddingClient
from recallum.memory import MemoryVisibility
from recallum.memory.limits import MemoryLimits
from recallum.memory.schemas import SourceType
from recallum.retrieval import reciprocal_rank_fusion
from recallum.skills import SkillValidationError
from recallum.skills.schemas import (
    ForgetSkillResult,
    GetSkillResult,
    MatchedSkill,
    MatchSkillsResult,
    SaveSkillResult,
    SimilarSkill,
    SkillOut,
)

logger = logging.getLogger("recallum.skills")

SOURCE_TYPES: tuple[str, ...] = get_args(SourceType)
MAX_SOURCE_REF_CHARS = 512
_WHITESPACE = re.compile(r"\s+")


class SkillService:
    """Coordinates validation, embeddings, retrieval and persistence for skills."""

    def __init__(
        self,
        repository: SkillRepository,
        embeddings: OllamaEmbeddingClient,
        limits: MemoryLimits | None = None,
    ) -> None:
        self._repo = repository
        self._embeddings = embeddings
        self._limits = limits if limits is not None else MemoryLimits()

    # ------------------------------------------------------------------
    # save_skill
    # ------------------------------------------------------------------

    async def save_skill(
        self,
        user_id: uuid.UUID,
        *,
        name: str,
        description: str,
        triggers: list[str],
        steps: list[str],
        constraints: str | None = None,
        project: str | None = None,
        scope: str | None = None,
        replace: bool = False,
        source_type: str | None = None,
        source_ref: str | None = None,
    ) -> SaveSkillResult:
        """Store a versioned procedure, deduplicating identical active steps."""
        normalized_name = self._normalize_text(name, field="name")
        normalized_description = self._normalize_text(description, field="description")
        normalized_triggers = self._normalize_list(triggers, field="triggers")
        normalized_steps = self._normalize_list(steps, field="steps")
        normalized_constraints = self._normalize_optional_text(constraints)
        resolved_scope, normalized_project = self._resolve_scope_project(scope, project)
        validated_source_type = self._validate_source_type(source_type)
        set_source_ref = source_ref is not None
        validated_source_ref = self._validate_source_ref(source_ref) if set_source_ref else None
        steps_digest = hashlib.sha256("\n".join(normalized_steps).encode("utf-8")).hexdigest()

        existing = await self._repo.find_active_by_name(
            user_id, scope=resolved_scope, project=normalized_project, name=normalized_name
        )
        if existing is not None:
            if existing.content_hash == steps_digest:
                return SaveSkillResult(skill=_to_skill_out(existing), created=False)
            if not replace:
                raise SkillValidationError(
                    f"an active skill named '{normalized_name}' already exists in this "
                    "scope with different steps; pass replace=True to save a new version"
                )
            searchable_text = self._searchable_text(
                normalized_description, normalized_triggers, normalized_steps
            )
            embedding = await self._embeddings.embed(searchable_text)
            replacement = await self._repo.supersede(
                user_id,
                existing.id,
                description=normalized_description,
                triggers=normalized_triggers,
                steps=normalized_steps,
                constraints=normalized_constraints,
                content_hash=steps_digest,
                embedding=embedding,
                source_type=validated_source_type,
                source_ref=validated_source_ref,
                set_source_ref=set_source_ref,
            )
            if replacement is None:
                # The active row was retired concurrently (e.g. forget_skill)
                # between the lookup above and the supersede transaction.
                raise SkillValidationError(
                    "the skill being replaced was removed concurrently; retry save_skill"
                )
            return SaveSkillResult(
                skill=_to_skill_out(replacement),
                created=True,
                similar=await self._similar_to(
                    user_id,
                    embedding,
                    scope=resolved_scope,
                    project=normalized_project,
                    exclude_id=replacement.id,
                ),
            )

        searchable_text = self._searchable_text(
            normalized_description, normalized_triggers, normalized_steps
        )
        embedding = await self._embeddings.embed(searchable_text)
        try:
            skill = await self._repo.create_skill(
                user_id,
                scope=resolved_scope,
                project=normalized_project,
                name=normalized_name,
                description=normalized_description,
                triggers=normalized_triggers,
                steps=normalized_steps,
                constraints=normalized_constraints,
                content_hash=steps_digest,
                embedding=embedding,
                source_type=validated_source_type or "unknown",
                source_ref=validated_source_ref,
            )
        except IntegrityError:
            # Concurrent insert won the race on the partial unique index.
            racing = await self._repo.find_active_by_name(
                user_id, scope=resolved_scope, project=normalized_project, name=normalized_name
            )
            if racing is not None:
                if racing.content_hash == steps_digest:
                    return SaveSkillResult(skill=_to_skill_out(racing), created=False)
                raise SkillValidationError(
                    f"an active skill named '{normalized_name}' already exists in this "
                    "scope with different steps; pass replace=True to save a new version"
                ) from None
            raise
        return SaveSkillResult(
            skill=_to_skill_out(skill),
            created=True,
            similar=await self._similar_to(
                user_id,
                embedding,
                scope=resolved_scope,
                project=normalized_project,
                exclude_id=skill.id,
            ),
        )

    async def _similar_to(
        self,
        user_id: uuid.UUID,
        embedding: list[float],
        *,
        scope: str,
        project: str | None,
        exclude_id: uuid.UUID,
    ) -> list[SimilarSkill]:
        """Pre-existing skills about the same procedure as the one just stored.

        Advisory only, like ``MemoryService._similar_to``: a failure here must
        not fail the write, and this never auto-merges or supersedes anything.
        """
        if self._limits.similar_max_results == 0:
            return []
        try:
            neighbours = await self._repo.similar_active(
                user_id,
                embedding,
                scope=scope,
                project=project,
                min_similarity=self._limits.similar_min_similarity,
                limit=self._limits.similar_max_results,
                exclude_id=exclude_id,
            )
        except Exception:
            logger.warning("similar-skill check failed; the skill was stored", exc_info=True)
            return []
        return [_to_similar_skill(n) for n in neighbours]

    # ------------------------------------------------------------------
    # match_skills
    # ------------------------------------------------------------------

    async def match_skills(
        self,
        user_id: uuid.UUID,
        *,
        query: str,
        project: str | None = None,
        scope: str | None = None,
        limit: StrictPositiveLimit | None = None,
    ) -> MatchSkillsResult:
        """Hybrid vector + full-text retrieval; degrades to textual on embed failure."""
        normalized_query = self._normalize_text(query, field="query")
        normalized_project = self._normalize_project(project)
        visibility = MemoryVisibility.from_filters(scope=scope, project=normalized_project)
        effective_limit = self._clamp_limit(
            limit, self._limits.recall_default_limit, self._limits.recall_max_limit
        )
        candidate_limit = min(60, max(effective_limit * 3, 10))

        mode = "hybrid"
        query_embedding: list[float] | None = None
        try:
            query_embedding = await self._embeddings.embed(normalized_query)
        except EmbeddingError:
            logger.warning("embedding unavailable for match_skills; using textual fallback")
            mode = "degraded_textual"

        pools = await self._repo.search_candidates(
            user_id,
            query=normalized_query,
            embedding=query_embedding,
            visibility=visibility,
            limit=candidate_limit,
        )
        fused = reciprocal_rank_fusion(
            [(list(pools.vector), 1.0), (list(pools.text), 1.0)],
            id_of=lambda scored: scored.skill.id,
            created_at_of=lambda scored: scored.skill.created_at,
        )
        results = [
            MatchedSkill(**_to_skill_out(scored.skill).model_dump(), score=score)
            for scored, score in fused[:effective_limit]
        ]
        return MatchSkillsResult(query=normalized_query, mode=mode, results=results)

    # ------------------------------------------------------------------
    # get_skill / forget_skill
    # ------------------------------------------------------------------

    async def get_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> GetSkillResult:
        """Fetch one active skill by id. Unknown, foreign and retired ids look identical."""
        skill = await self._repo.get_active(user_id, skill_id)
        if skill is None:
            return GetSkillResult(found=False)
        return GetSkillResult(found=True, skill=_to_skill_out(skill))

    async def forget_skill(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> ForgetSkillResult:
        """Logical delete; unknown and foreign ids both report not forgotten."""
        forgotten = await self._repo.soft_delete(user_id, skill_id)
        return ForgetSkillResult(id=skill_id, forgotten=forgotten)

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------

    def _searchable_text(self, description: str, triggers: list[str], steps: list[str]) -> str:
        """Embedding input and tsvector source: description, then triggers, then steps."""
        return " ".join([description, *triggers, *steps])

    def _resolve_scope_project(
        self, scope: str | None, project: str | None
    ) -> tuple[str, str | None]:
        normalized_project = self._normalize_project(project)
        if scope == "global":
            if normalized_project is not None:
                raise SkillValidationError("project must not be set when scope is 'global'")
            return "global", None
        if scope == "project":
            if normalized_project is None:
                raise SkillValidationError("project is required when scope is 'project'")
            return "project", normalized_project
        if scope is not None:
            raise SkillValidationError("scope must be 'global' or 'project'")
        if normalized_project is not None:
            return "project", normalized_project
        return "global", None

    def _clamp_limit(self, requested: int | None, default: int, maximum: int) -> int:
        if requested is None:
            return default
        if not isinstance(requested, int) or isinstance(requested, bool):
            raise SkillValidationError("limit must be an integer")
        return max(1, min(requested, maximum))

    def _normalize_text(self, value: str, *, field: str) -> str:
        if value is None:
            raise SkillValidationError(f"{field} must not be empty")
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()
        if not normalized:
            raise SkillValidationError(f"{field} must not be empty")
        return normalized

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()
        return normalized or None

    def _normalize_list(self, values: list[str], *, field: str) -> list[str]:
        if not isinstance(values, list) or not values:
            raise SkillValidationError(f"{field} must be a non-empty list of strings")
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise SkillValidationError(f"{field} entries must be strings")
            item = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()
            if item:
                normalized.append(item)
        if not normalized:
            raise SkillValidationError(f"{field} must contain at least one non-empty entry")
        return normalized

    def _normalize_project(self, project: str | None) -> str | None:
        if project is None:
            return None
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", project)).strip()
        if not normalized:
            return None
        if len(normalized) > self._limits.max_project_chars:
            raise SkillValidationError(
                f"project exceeds {self._limits.max_project_chars} characters"
            )
        return normalized

    def _validate_source_type(self, source_type: str | None) -> str | None:
        if source_type is None:
            return None
        if source_type not in SOURCE_TYPES:
            raise SkillValidationError(
                f"unknown source_type '{source_type}'; expected one of {', '.join(SOURCE_TYPES)}"
            )
        return source_type

    def _validate_source_ref(self, source_ref: str | None) -> str | None:
        if source_ref is None:
            return None
        if not isinstance(source_ref, str):
            raise SkillValidationError("source_ref must be a string")
        normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", source_ref)).strip()
        if not normalized:
            return None
        if len(normalized) > MAX_SOURCE_REF_CHARS:
            raise SkillValidationError(f"source_ref exceeds {MAX_SOURCE_REF_CHARS} characters")
        return normalized


def _to_skill_out(skill) -> SkillOut:
    return SkillOut(
        id=skill.id,
        scope=skill.scope,
        project=skill.project,
        name=skill.name,
        description=skill.description,
        triggers=list(skill.triggers or []),
        steps=list(skill.steps or []),
        constraints=skill.constraints,
        version=skill.version,
        source_type=getattr(skill, "source_type", None) or "unknown",
        source_ref=getattr(skill, "source_ref", None),
        created_at=skill.created_at,
    )


def _to_similar_skill(neighbour: ScoredSkill) -> SimilarSkill:
    return SimilarSkill(
        id=neighbour.skill.id,
        name=neighbour.skill.name,
        description=neighbour.skill.description,
        version=neighbour.skill.version,
        similarity=neighbour.score,
        created_at=neighbour.skill.created_at,
    )
