"""Add freshness and usage signals to memories.

``reconfirmed_at`` records the last time identical content was re-stored (the
exact-dedup path), ``last_recalled_at``/``recall_count`` record when a memory
was served in ``recall`` or ``context`` results. No backfill: NULL / 0 mean
"no signal yet", which is the truth for every pre-existing row. No indexes:
nothing filters by these columns; they are read alongside rows already
selected by other predicates.
"""

from __future__ import annotations

from alembic import op

revision = "0008_agent_synergy"
down_revision = "0007_tool_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN reconfirmed_at TIMESTAMPTZ,
            ADD COLUMN last_recalled_at TIMESTAMPTZ,
            ADD COLUMN recall_count INTEGER NOT NULL DEFAULT 0
                CHECK (recall_count >= 0)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            DROP COLUMN reconfirmed_at,
            DROP COLUMN last_recalled_at,
            DROP COLUMN recall_count
        """
    )
