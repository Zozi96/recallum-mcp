"""Fix text retrieval, keep soft-deleted rows out of the HNSW graph, and record
which model produced each embedding.

Three problems this migration addresses
---------------------------------------
1. ``content_tsv`` was generated with the ``simple`` configuration, which does
   no stemming and removes no stopwords. Combined with ``websearch_to_tsquery``
   (which ANDs every term), a natural-language query such as "what are my
   python preferences" required the lexemes ``what & are & my & python &
   preferences`` to all be present, so the textual half of hybrid retrieval
   matched essentially nothing -- and ``recall`` returned nothing at all when
   Ollama was down and the vector half was unavailable. The column is rebuilt
   with the ``english`` configuration; the matching OR-query construction lives
   in ``MemoryRepository.search_text``.

   The configuration name is duplicated here as a literal on purpose: a
   migration is a historical record and must not change meaning when
   ``recallum.config.TEXT_SEARCH_CONFIG`` is edited later. An integration test
   asserts the live column and that constant still agree.

2. The HNSW index covered soft-deleted rows, which are only removed by the
   manual ``purge_deleted.sh``. With ``hnsw.iterative_scan = strict_order``
   those rows were walked and discarded on every search, burning scan budget.
   The index becomes partial on ``deleted_at IS NULL``.

3. ``memories`` recorded no embedding provenance, so changing
   ``RECALLUM__OLLAMA__MODEL`` to another 768-dimension model silently
   invalidated every stored vector with no error anywhere.

Rewrite cost
------------
Re-adding a STORED generated column rewrites the table and rebuilds its
indexes, so the steps are ordered to build each index exactly once: drop the
GIN index, swap the column, then create both the HNSW and GIN indexes. On a
personal-scale corpus this is seconds; it does take an ACCESS EXCLUSIVE lock,
so run it during the normal migrate step, not against a live serving process.
"""

from __future__ import annotations

from alembic import op

revision = "0003_text_search_provenance"
down_revision = "0002_require_pgvector_0_8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Embedding provenance. Nullable: existing rows predate tracking and we
    #    cannot know retroactively which model wrote them.
    op.execute("ALTER TABLE memories ADD COLUMN embedding_model TEXT")

    # 2. Rebuild content_tsv with a stemming, stopword-aware configuration.
    #    A generated column's expression cannot be altered in place.
    op.execute("DROP INDEX ix_memories_content_tsv")
    op.execute("ALTER TABLE memories DROP COLUMN content_tsv")
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN content_tsv tsvector GENERATED ALWAYS AS (
                to_tsvector('english', content)
            ) STORED
        """
    )

    # 3. Keep soft-deleted rows out of the vector graph, then rebuild the GIN
    #    index. Both are created after the rewrite so neither is built twice.
    op.execute("DROP INDEX ix_memories_embedding_hnsw")
    op.execute(
        """
        CREATE INDEX ix_memories_embedding_hnsw
            ON memories USING hnsw (embedding vector_cosine_ops)
            WHERE deleted_at IS NULL
        """
    )
    op.execute("CREATE INDEX ix_memories_content_tsv ON memories USING gin (content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_memories_content_tsv")
    op.execute("ALTER TABLE memories DROP COLUMN content_tsv")
    op.execute(
        """
        ALTER TABLE memories
            ADD COLUMN content_tsv tsvector GENERATED ALWAYS AS (
                to_tsvector('simple', content)
            ) STORED
        """
    )
    op.execute("DROP INDEX ix_memories_embedding_hnsw")
    op.execute(
        """
        CREATE INDEX ix_memories_embedding_hnsw
            ON memories USING hnsw (embedding vector_cosine_ops)
        """
    )
    op.execute("CREATE INDEX ix_memories_content_tsv ON memories USING gin (content_tsv)")
    op.execute("ALTER TABLE memories DROP COLUMN embedding_model")
