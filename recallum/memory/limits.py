"""Memory validation, retrieval and ranking tunables value object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MemoryLimits(BaseModel):
    """Memory validation, retrieval and ranking tunables."""

    model_config = ConfigDict(frozen=True)

    # How much one full sweep of the importance ranking is worth against one
    # retrieval signal in recall's fusion. At the default, importance reorders
    # candidates that relevance already scored close together and cannot
    # displace a clearly better match; 0.0 restores pure relevance ordering.
    # Capped below 1.0 so it can never outweigh a retrieval signal outright.
    recall_importance_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    # Cosine similarity at or above which a pre-existing memory is reported
    # back from ``remember`` as possibly about the same subject. Tuned to catch
    # restatements and contradictions while ignoring merely related memories;
    # 1.0 effectively disables the check, since exact repeats are already
    # deduplicated by content hash before it runs.
    similar_min_similarity: float = Field(default=0.85, ge=0.0, le=1.0)
    similar_max_results: int = Field(default=3, ge=0, le=10)

    # The graph is an intentionally bounded projection. Pairwise comparison is
    # quadratic, so these conservative server-owned ceilings are part of the
    # safety boundary rather than client preferences.
    graph_max_nodes: int = Field(default=200, gt=0, le=500)
    graph_max_neighbours: int = Field(default=4, gt=0, le=10)
    graph_min_similarity: float = Field(default=0.72, ge=0.5, le=1.0)

    max_content_chars: int = Field(default=4000, gt=0)
    max_project_chars: int = Field(default=200, gt=0)
    max_metadata_bytes: int = Field(default=2048, gt=0)
    max_metadata_keys: int = Field(default=16, gt=0)
    recall_default_limit: int = Field(default=10, gt=0)
    recall_max_limit: int = Field(default=50, gt=0)
    list_default_limit: int = Field(default=50, gt=0)
    list_max_limit: int = Field(default=100, gt=0)
    list_max_offset: int = Field(default=10_000, ge=0)
    context_default_max_items: int = Field(default=20, gt=0)
    context_max_items_cap: int = Field(default=50, gt=0)
    context_default_max_chars: int = Field(default=6000, gt=0)
    context_max_chars_cap: int = Field(default=20000, gt=0)
