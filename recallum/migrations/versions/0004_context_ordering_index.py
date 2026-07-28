"""Index the ordering ``context`` reads by.

``most_important_active`` orders by ``(importance DESC, created_at DESC, id)``
within a user, but the only covering index was ``(user_id, created_at DESC)``,
so every ``context`` call sorted its rows in memory. ``context`` is the tool an
agent runs at the start of every session and it fetches the cap plus one row
twice (once for global scope, once for the project), so the sort was on the
hottest read path in the server.

The index is partial on ``deleted_at IS NULL`` to match the query and to keep
soft-deleted rows out of it, and carries ``id`` so the whole ordering -- including
the final deterministic tie-break -- is satisfied by an index scan.
"""

from __future__ import annotations

from alembic import op

revision = "0004_context_ordering_index"
down_revision = "0003_text_search_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX ix_memories_user_importance
            ON memories (user_id, importance DESC, created_at DESC, id)
            WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_memories_user_importance")
