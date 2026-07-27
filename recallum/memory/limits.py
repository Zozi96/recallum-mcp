"""Memory validation and retrieval limits value object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MemoryLimits(BaseModel):
    """Memory validation and retrieval limits."""

    model_config = ConfigDict(frozen=True)

    max_content_chars: int = Field(default=4000, gt=0)
    max_project_chars: int = Field(default=200, gt=0)
    max_metadata_bytes: int = Field(default=2048, gt=0)
    max_metadata_keys: int = Field(default=16, gt=0)
    recall_default_limit: int = Field(default=10, gt=0)
    recall_max_limit: int = Field(default=50, gt=0)
    list_default_limit: int = Field(default=50, gt=0)
    list_max_limit: int = Field(default=100, gt=0)
    context_default_max_items: int = Field(default=20, gt=0)
    context_max_items_cap: int = Field(default=50, gt=0)
    context_default_max_chars: int = Field(default=6000, gt=0)
    context_max_chars_cap: int = Field(default=20000, gt=0)
