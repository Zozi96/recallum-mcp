"""Record that a memory was replaced rather than merely removed.

Until now the only way to correct a memory was ``forget`` plus ``remember``,
which loses the link between the two and, in between, loses the memory
entirely. Contradictory statements therefore accumulated with nothing marking
which one won.

``superseded_by`` points at the replacement. Superseding also stamps
``deleted_at``, so the replaced row drops out of every active query through the
partial indexes that already exist -- including the dedup index, which is what
frees the old content hash for reuse. The column exists to record *why* a row
left the active set, so "the user forgot this" stays distinguishable from "this
fact changed".

``ON DELETE SET NULL`` keeps ``purge_deleted.sh`` working: hard-deleting a
replacement must not be blocked by an ancestor still pointing at it.
"""

from __future__ import annotations

from alembic import op

revision = "0005_supersession"
down_revision = "0004_context_ordering_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN superseded_by UUID
            REFERENCES memories (id) ON DELETE SET NULL
        """
    )
    # Walking a supersession chain is rare, but the FK makes PostgreSQL check
    # for referencing rows on every delete, and purges delete in bulk.
    op.execute(
        """
        CREATE INDEX ix_memories_superseded_by
            ON memories (superseded_by)
            WHERE superseded_by IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_memories_superseded_by")
    op.execute("ALTER TABLE memories DROP COLUMN superseded_by")
