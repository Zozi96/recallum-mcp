"""SQLAlchemy declarative models mirroring the Alembic-owned schema.

The application never creates tables itself; these models exist for queries
and must stay in sync with the migrations.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recallum.config import EMBEDDING_DIMENSIONS, TEXT_SEARCH_CONFIG
from recallum.db.base import Base


class User(Base):
    """A human owner of memories. Identified by API keys, never by agents."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    memory_generation: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), nullable=False
    )
    active_memory_count: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), default=0, nullable=False
    )

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list[Memory]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memory_profiles: Mapped[list[MemoryProfile]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tool_activity: Mapped[list[ToolActivity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    web_sessions: Mapped[list[WebSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiKey(Base):
    """A revocable bearer credential. Only the SHA-256 hash is persisted."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_keys")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class WebSession(Base):
    """A browser credential; only its SHA-256 token hash is stored."""

    __tablename__ = "web_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("web_sessions.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="web_sessions")


class Memory(Base):
    """An atomic memory: preference, decision, constraint, or fact."""

    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("scope IN ('global', 'project')", name="ck_memories_scope"),
        CheckConstraint(
            "category IN ('preference', 'decision', 'constraint', 'fact')",
            name="ck_memories_category",
        ),
        CheckConstraint("importance BETWEEN 0 AND 10", name="ck_memories_importance"),
        CheckConstraint("(scope = 'project') = (project IS NOT NULL)", name="ck_memories_project"),
        CheckConstraint(
            "source_type IN ('agent', 'user', 'bootstrap', 'unknown')",
            name="ck_memories_source_type",
        ),
        CheckConstraint(
            "kind IN ('failure', 'solution', 'architecture', 'convention', 'todo', 'command')",
            name="ck_memories_kind",
        ),
        Index(
            "ix_memories_user_active_created",
            "user_id",
            text("created_at DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Serves most_important_active, which drives every ``context`` call.
        Index(
            "ix_memories_user_importance",
            "user_id",
            text("importance DESC"),
            text("created_at DESC"),
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    project: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    # Orthogonal coding facet -- what the memory is (failure, solution,
    # architecture, convention, todo, command) -- distinct from ``category``,
    # which is the lifecycle facet (preference/decision/constraint/fact).
    # NULL means unclassified; existing rows stay NULL.
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    # Which model produced ``embedding``. NULL means "written before provenance
    # was tracked". Vectors from different models are not comparable, so the
    # vector search leg ranks only rows whose provenance is NULL or the
    # configured model; positively mismatched rows stay reachable through the
    # textual leg until ``recallum-admin reembed`` restamps them.
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    source_client: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unknown", server_default=text("'unknown'")
    )
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Freshness and usage signals. ``reconfirmed_at`` is the last time identical
    # content was re-stored (exact dedup); ``last_recalled_at``/``recall_count``
    # track matching a ``recall`` query, while ``context_count`` tracks riding
    # along in a ``context`` snapshot. Snapshot serves echo importance, not
    # relevance, so the two counters are deliberately separate: only recall
    # hits may ever feed the usage voter. NULL / 0 mean "no signal".
    reconfirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_recalled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    context_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Cumulative count of explicit reconfirmations, distinct from the serve
    # counts above: an agent verifying a claim against reality is a different
    # (and, unlike serve counts, not yet ranking-poisoned) utility signal.
    # A replacement row from ``update``/``merge`` starts at 0 -- a new claim
    # has not itself been re-verified. Does not feed ranking by default.
    reconfirm_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional declared expiry for short-lived "working memory" (e.g. "branch X
    # is blocked this week"). NULL means no expiry -- the historical default,
    # unaffected. Once past, the row is excluded from every active-selection
    # predicate but never physically deleted: no background purge job, this is
    # a lazy read-time filter only, same shape as ``deleted_at`` but distinct
    # from it -- an expired row is not "forgotten", it is just not served.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The memory that replaced this one. Superseding also sets ``deleted_at``,
    # so a replaced row leaves every active query through the filter that
    # already exists; this column only records *why* it left, distinguishing
    # "the user forgot it" from "the fact changed". ON DELETE SET NULL so the
    # purge job can hard-delete a replacement without stranding its ancestor.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    content_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(f"to_tsvector('{TEXT_SEARCH_CONFIG}', content)", persisted=True),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="memories")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= datetime.now(UTC)


class MemoryProfile(Base):
    """Materialized always-on profile projection for one user key.

    ``project == ""`` is the user-global profile; a non-empty string is a
    project-scoped key. Items are denormalized snapshots of active memories.
    """

    __tablename__ = "memory_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    static_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    dynamic_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    source_memory_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1)

    user: Mapped[User] = relationship(back_populates="memory_profiles")


class ToolActivity(Base):
    """Content-free operational metadata for one authenticated MCP tool call."""

    __tablename__ = "tool_activity"
    __table_args__ = (
        CheckConstraint("duration_ms >= 0", name="ck_tool_activity_duration_ms"),
        CheckConstraint("result_count >= 0", name="ck_tool_activity_result_count"),
        Index(
            "ix_tool_activity_user_created_at",
            "user_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    duration_ms: Mapped[int] = mapped_column(nullable=False)
    result_count: Mapped[int] = mapped_column(nullable=False, default=0)
    degraded: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    failed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="tool_activity")
