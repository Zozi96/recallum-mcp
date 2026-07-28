"""SQLAlchemy declarative models mirroring the Alembic-owned schema.

The application never creates tables itself; these models exist for queries
and must stay in sync with the migrations.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
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

    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list[Memory]] = relationship(
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
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    # Which model produced ``embedding``. NULL means "written before provenance
    # was tracked". Vectors from different models are not comparable, so a
    # mismatch makes cosine similarity meaningless; startup warns rather than
    # hiding rows, because silently dropping memories is the worse failure.
    embedding_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    source_client: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
