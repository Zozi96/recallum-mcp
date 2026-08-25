"""Optional coding ``kind`` on each memory row, orthogonal to ``category``.

``kind`` classifies what a memory is for coding retrieval strategies
(failure, solution, architecture, convention, todo, command), while
``category`` keeps classifying the lifecycle facet (preference, decision,
constraint, fact). NULL means unclassified. Existing rows backfill to NULL.
"""

from __future__ import annotations

from alembic import op

revision = "0017_coding_memory_kinds"
down_revision = "0016_memory_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN kind TEXT,
            ADD CONSTRAINT ck_memories_kind
                CHECK (kind IN
                    ('failure', 'solution', 'architecture', 'convention', 'todo', 'command')
                )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP CONSTRAINT ck_memories_kind")
    op.execute("ALTER TABLE memories DROP COLUMN kind")
