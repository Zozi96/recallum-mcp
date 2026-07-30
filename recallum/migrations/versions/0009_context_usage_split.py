"""Split context snapshot serves from recall hits in usage accounting.

``recall_count``/``last_recalled_at`` previously counted every serve — recall
hits and ``context`` snapshot appearances alike. High-importance memories ride
along in nearly every snapshot, so the combined counter measured "is
important", not "matches queries", pre-poisoning the signal
``recall_usage_weight`` is waiting on before it may take a non-zero value.
``context_count`` takes over the snapshot serves; from this revision on,
``recall_count`` moves only when a memory is served by ``recall``.

No backfill: serves recorded before this revision cannot be unmixed, so
pre-existing ``recall_count`` values are an upper bound on genuine recall
hits. No index: nothing filters by these columns; they are read alongside
rows already selected by other predicates.
"""

from __future__ import annotations

from alembic import op

revision = "0009_context_usage_split"
down_revision = "0008_agent_synergy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN context_count INTEGER NOT NULL DEFAULT 0
                CHECK (context_count >= 0)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN context_count")
