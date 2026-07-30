"""Trigram index for the fuzzy lexical retrieval leg.

``content_tsv`` is built with the English text-search configuration, so
Spanish content gets English stemming and code identifiers are matched only
whole. pg_trgm word-similarity is language-neutral and typo-tolerant, giving
recall a third leg that catches what the tsvector leg mangles and what the
vector leg cannot reach when embeddings are down.

pg_trgm is a trusted extension (CREATE privilege suffices, no superuser).
The index is partial on active rows, matching every retrieval predicate;
the extension is deliberately not dropped on downgrade because other
objects in the database may have started depending on it.
"""

from __future__ import annotations

from alembic import op

revision = "0010_trigram_leg"
down_revision = "0009_context_usage_split"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        """
        CREATE INDEX ix_memories_content_trgm
            ON memories USING gin (content gin_trgm_ops)
            WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memories_content_trgm")
