"""Public schemas returned by the skill tools.

These shapes are what MCP clients see. They deliberately never expose
``user_id``: identity always comes from the authenticated key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from recallum.memory.schemas import SourceType

MatchMode = Literal["hybrid", "degraded_textual"]


class SkillOut(BaseModel):
    """A stored skill as returned to agents."""

    id: uuid.UUID
    scope: Literal["global", "project"]
    project: str | None = None
    name: str
    description: str
    triggers: list[str]
    steps: list[str]
    constraints: str | None = None
    version: int
    source_type: SourceType = "unknown"
    source_ref: str | None = None
    created_at: datetime


class SimilarSkill(BaseModel):
    """An existing skill close enough to a new one to be about the same procedure."""

    id: uuid.UUID
    name: str
    description: str
    version: int
    similarity: float
    created_at: datetime


class SaveSkillResult(BaseModel):
    """Outcome of ``save_skill``; ``created`` is False for deduplicated stores."""

    skill: SkillOut
    created: bool
    similar: list[SimilarSkill] = Field(default_factory=list)


class MatchedSkill(SkillOut):
    """A skill plus its fused relevance score."""

    score: float


class MatchSkillsResult(BaseModel):
    """Outcome of ``match_skills`` with the retrieval mode used."""

    query: str
    mode: MatchMode
    results: list[MatchedSkill]


class GetSkillResult(BaseModel):
    """Outcome of ``get_skill``; unknown, foreign and retired ids look identical."""

    found: bool
    skill: SkillOut | None = None


class ForgetSkillResult(BaseModel):
    """Outcome of ``forget_skill``; missing and foreign ids look identical."""

    id: uuid.UUID
    forgotten: bool
