"""Cumulative reconfirmation counter, separate from serve-count usage signals.

A measured decision (docs/operations.md, 2026-08-22) found the serve-count
usage vote (``recall_count``) degrades ranking: high-usage rows displace
correct but weakly-matched candidates. Reconfirmation is a different kind of
signal -- an agent explicitly verifying a memory against reality, not a
passive serve. Only ``reconfirmed_at`` (the latest timestamp) survived until
now; the cumulative count was lost on every re-stamp. ``reconfirm_count``
keeps that history so it can be evaluated on its own, independent of the
serve-count experiment above. It does not feed ranking by default.

No backfill: reconfirmations before this revision left no count, only the
last timestamp. No index: nothing filters by this column; it is read
alongside rows already selected by other predicates.
"""

from __future__ import annotations

from alembic import op

revision = "0014_reconfirm_count"
down_revision = "0013_admin_memory_aggregates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN reconfirm_count INTEGER NOT NULL DEFAULT 0
                CHECK (reconfirm_count >= 0)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN reconfirm_count")
