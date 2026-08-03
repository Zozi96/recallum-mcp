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

    # How many focus-relevant memories a task-focused ``context`` call may add
    # on top of the importance-ranked snapshot. The focus only ever adds
    # candidates; it never displaces preferences or constraints.
    context_focus_limit: int = Field(default=10, gt=0, le=30)

    # Minimum leftover character budget worth filling with a clipped item.
    # Below this, clipping would produce a fragment too short to act on, so
    # assembly stops instead -- keeping strict importance order rather than
    # skipping long items and back-filling with shorter, less important ones.
    context_truncate_floor: int = Field(default=200, gt=0)

    # Materialized profile selection (static = always-on, dynamic = recent).
    # Static prefers preference/constraint; other categories need high
    # importance. Caps keep the always-on layer small so context remainder
    # stays usable for task/project snapshot.
    profile_static_min_importance: int = Field(default=8, ge=0, le=10)
    profile_static_max_items: int = Field(default=12, gt=0, le=50)
    profile_static_max_chars: int = Field(default=2000, gt=0)
    profile_dynamic_window_days: int = Field(default=14, gt=0)
    profile_dynamic_max_items: int = Field(default=8, gt=0, le=50)
    profile_dynamic_max_chars: int = Field(default=1500, gt=0)
    # Reserved share of a context call for the assembled profile block.
    # Defaults sit under ~40% of context_default_max_chars so focus/importance
    # still receive budget.
    profile_context_max_items: int = Field(default=16, gt=0, le=50)
    profile_context_max_chars: int = Field(default=2400, gt=0)

    # Upper bound on ``remember_batch`` items. Small on purpose: a capture scan
    # should be a few high-signal atoms, not a session recap.
    batch_max_items: int = Field(default=10, gt=0, le=20)

    # Upper bound on memories one ``merge`` may consolidate. Small on purpose:
    # a merge is a considered editorial act over memories the agent has read,
    # not a bulk compaction pass.
    merge_max_sources: int = Field(default=10, gt=1, le=20)

    # Usage's vote in recall fusion, same competition-ranking mechanism as
    # importance. Ships at 0.0 (no effect) so ``recall_count`` accumulates real
    # data before it is allowed to influence ranking -- a non-zero weight is a
    # rich-get-richer loop and must be a deliberate, measured choice.
    recall_usage_weight: float = Field(default=0.0, ge=0.0, le=1.0)

    # Days after which a memory that was never reconfirmed or re-stored counts
    # as stale: context items carry ``stale: true`` past this age, and
    # ``list_memories(stale=true)`` is the verification queue. Re-storing
    # identical content stamps ``reconfirmed_at`` and resets the clock;
    # ``update`` replaces the row outright.
    stale_after_days: int = Field(default=90, gt=0)

    # The trigram leg's vote in recall fusion, relative to one full retrieval
    # signal. It is a safety net for what the other legs miss -- typos,
    # identifier fragments, and words the English full-text dictionary
    # mangles -- so it ships at half strength: enough to surface rows the
    # primary signals never found and to break ties, never enough to outvote
    # a genuine semantic or exact-text match. 0.0 disables the leg and skips
    # its query entirely.
    recall_trigram_weight: float = Field(default=0.5, ge=0.0, le=1.0)

    # Minimum pg_trgm word_similarity for a trigram candidate. 0.4 keeps
    # one-letter typos on medium-length words and camelCase fragments while
    # rejecting accidental trigram overlap; pg_trgm's own default (0.6)
    # misses realistic typos, and short-word transpositions are beyond any
    # trigram threshold.
    trigram_min_word_similarity: float = Field(default=0.4, gt=0.0, le=1.0)
