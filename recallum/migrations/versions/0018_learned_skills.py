"""Learned skills: versioned procedures, distinct from atomic memories.

A skill says "when this happens, follow this procedure" -- a separate table
from ``memories``, never a memory ``category``, so it cannot poison memory
retrieval or profile static selection. Mirrors the memory isolation model:
RLS forced on ``app.current_user_id``, an HNSW index over the embedding, and
a GIN index over a generated tsvector built from ``description``, ``triggers``
and ``steps``. ``superseded_by`` and ``deleted_at`` follow the same
supersession shape memories already use. The partial unique index enforces
at most one active skill per ``(user, scope, project, name)`` bucket.

``array_to_string`` is STABLE in PostgreSQL (a polymorphic-array function is
never marked IMMUTABLE), which a GENERATED column rejects; a trivial SQL
wrapper re-declares the same call as IMMUTABLE, since concatenating a
``text[]`` is in fact deterministic.
"""

from __future__ import annotations

from alembic import op

revision = "0018_learned_skills"
down_revision = "0017_coding_memory_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION recallum_immutable_array_to_string(text[], text) RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog
            AS $$ SELECT pg_catalog.array_to_string($1, $2) $$
        """
    )

    op.execute(
        """
        CREATE TABLE skills (
            id            UUID PRIMARY KEY,
            user_id       UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            scope         TEXT NOT NULL CHECK (scope IN ('global', 'project')),
            project       TEXT,
            name          TEXT NOT NULL,
            description   TEXT NOT NULL,
            triggers      TEXT[] NOT NULL,
            steps         TEXT[] NOT NULL,
            constraints   TEXT,
            version       INTEGER NOT NULL DEFAULT 1,
            content_hash  CHAR(64) NOT NULL,
            embedding     vector(768) NOT NULL,
            source_type   TEXT NOT NULL DEFAULT 'unknown' CHECK (
                              source_type IN ('agent', 'user', 'bootstrap', 'unknown')
                          ),
            source_ref    TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at    TIMESTAMPTZ,
            superseded_by UUID REFERENCES skills (id) ON DELETE SET NULL,
            search_tsv    tsvector GENERATED ALWAYS AS (
                              to_tsvector('english',
                                  description || ' ' ||
                                  recallum_immutable_array_to_string(triggers, ' ') || ' ' ||
                                  recallum_immutable_array_to_string(steps, ' ')
                              )
                          ) STORED,
            CHECK ((scope = 'project') = (project IS NOT NULL))
        )
        """
    )

    op.execute(
        """
        CREATE INDEX ix_skills_user_active_created
            ON skills (user_id, created_at DESC)
            WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_skills_superseded_by
            ON skills (superseded_by)
            WHERE superseded_by IS NOT NULL
        """
    )

    # At most one active skill per user/scope/project/name bucket.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_skills_active_name
            ON skills (user_id, scope, COALESCE(project, ''), name)
            WHERE deleted_at IS NULL
        """
    )

    # Semantic candidates: cosine-distance HNSW.
    op.execute(
        """
        CREATE INDEX ix_skills_embedding_hnsw
            ON skills USING hnsw (embedding vector_cosine_ops)
        """
    )

    # Textual candidates: GIN over the english-config tsvector.
    op.execute("CREATE INDEX ix_skills_search_tsv ON skills USING gin (search_tsv)")

    # Row-Level Security: skills are hard-isolated (forced even for owner).
    op.execute("ALTER TABLE skills ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE skills FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY skills_user_isolation ON skills
            FOR ALL
            USING (user_id::text = current_setting('app.current_user_id', true))
            WITH CHECK (user_id::text = current_setting('app.current_user_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS skills")
    op.execute("DROP FUNCTION IF EXISTS recallum_immutable_array_to_string(text[], text)")
