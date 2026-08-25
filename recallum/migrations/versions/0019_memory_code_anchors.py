"""Structured code anchors on a memory: file, symbol, or module references.

A child table rather than a JSONB column on ``memories``: the closed decision
in ``openspec/changes/memory-code-anchors`` picks it as simpler to index
(btree on ``(anchor_type, identifier)``) and to constrain (a CHECK on the
type, a unique triple per memory). The column is named ``anchor_type`` --
not ``kind`` as design.md sketches it -- because ``memories.kind`` already
exists (0017) with an unrelated meaning; the MCP/API field stays ``type``.

Recallum does not build a code graph: this table only lets a memory declare
a verbatim link an agent asserted, matched later by exact NFC-normalized
equality, never a graph walk or a repository parse.

Isolation: ``memory_anchors`` carries no ``user_id`` of its own. Its RLS
policy proves ownership through a correlated subquery against ``memories``
(itself force-RLS'd on ``user_id``), so a row is reachable only via its
owning memory's owner -- the same guarantee a direct ``user_id`` column and
policy would give, without duplicating that column onto every anchor row.
"""

from __future__ import annotations

from alembic import op

revision = "0019_memory_code_anchors"
down_revision = "0018_learned_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_anchors (
            id          UUID PRIMARY KEY,
            memory_id   UUID NOT NULL REFERENCES memories (id) ON DELETE CASCADE,
            anchor_type TEXT NOT NULL,
            identifier  TEXT NOT NULL,
            CONSTRAINT ck_memory_anchors_type CHECK (anchor_type IN ('file', 'symbol', 'module')),
            CONSTRAINT uq_memory_anchors_identifier UNIQUE (memory_id, anchor_type, identifier)
        )
        """
    )

    # Serves the recall pre-filter: exact (anchor_type, identifier) lookup
    # before RRF fusion.
    op.execute(
        """
        CREATE INDEX ix_memory_anchors_type_identifier
            ON memory_anchors (anchor_type, identifier)
        """
    )

    # Row-Level Security: no user_id column here, so ownership is proven by
    # correlated subquery against memories (itself force-RLS'd), not a direct
    # column comparison.
    op.execute("ALTER TABLE memory_anchors ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE memory_anchors FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY memory_anchors_user_isolation ON memory_anchors
            FOR ALL
            USING (
                EXISTS (
                    SELECT 1 FROM memories
                    WHERE memories.id = memory_anchors.memory_id
                      AND memories.user_id::text = current_setting('app.current_user_id', true)
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM memories
                    WHERE memories.id = memory_anchors.memory_id
                      AND memories.user_id::text = current_setting('app.current_user_id', true)
                )
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_anchors")
