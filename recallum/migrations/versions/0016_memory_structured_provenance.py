"""Optional structured provenance on each memory row.

``source_type`` records who asserted the claim (agent, user, bootstrap, or
unknown). ``source_ref`` is a short path/commit/file id, never a transcript.
Existing rows backfill to ``unknown`` / NULL. Writers may omit both fields.
"""

from __future__ import annotations

from alembic import op

revision = "0016_memory_provenance"
down_revision = "0015_memory_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN source_type TEXT NOT NULL DEFAULT 'unknown',
            ADD COLUMN source_ref TEXT,
            ADD CONSTRAINT ck_memories_source_type
                CHECK (source_type IN ('agent', 'user', 'bootstrap', 'unknown'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP CONSTRAINT ck_memories_source_type")
    op.execute("ALTER TABLE memories DROP COLUMN source_ref")
    op.execute("ALTER TABLE memories DROP COLUMN source_type")
