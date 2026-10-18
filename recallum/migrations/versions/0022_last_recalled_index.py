"""Partial index for dynamic selection by last_recalled_at.

``context_snapshot`` and ``list_active_for_profile`` both filter active rows
with ``last_recalled_at IS NOT NULL`` and order by ``last_recalled_at DESC``.
The partial predicate keeps never-recalled and soft-deleted rows out of the
index. Tie-break columns (``created_at``, ``id``) stay out: the leading key
is what the planner can use.
"""

from __future__ import annotations

from alembic import op

revision = "0022_last_recalled_index"
down_revision = "0021_skills_hnsw_partial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_memories_user_last_recalled
            ON memories (user_id, last_recalled_at DESC)
            WHERE deleted_at IS NULL AND last_recalled_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_memories_user_last_recalled")
