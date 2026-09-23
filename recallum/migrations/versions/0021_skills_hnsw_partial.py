"""Keep soft-deleted skills out of the HNSW vector graph.

``0018_learned_skills`` created ``ix_skills_embedding_hnsw`` without the
``WHERE deleted_at IS NULL`` predicate that ``0003`` gave the memories index,
so retired skill rows stay in the graph forever. Every skill candidate query
filters ``deleted_at IS NULL``, so the partial index is a strict improvement:
smaller graph, same result set. The downgrade restores the full index.
"""

from __future__ import annotations

from alembic import op

revision = "0021_skills_hnsw_partial"
down_revision = "0020_invalidate_memory_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX ix_skills_embedding_hnsw")
    op.execute(
        """
        CREATE INDEX ix_skills_embedding_hnsw
            ON skills USING hnsw (embedding vector_cosine_ops)
            WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_skills_embedding_hnsw")
    op.execute(
        """
        CREATE INDEX ix_skills_embedding_hnsw
            ON skills USING hnsw (embedding vector_cosine_ops)
        """
    )
