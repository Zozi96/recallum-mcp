"""Require pgvector 0.8 for filtered HNSW iterative scans."""

from __future__ import annotations

from alembic import op

revision = "0002_require_pgvector_0_8"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            installed integer[];
        BEGIN
            SELECT string_to_array(extversion, '.')::integer[]
              INTO installed
              FROM pg_extension
             WHERE extname = 'vector';

            IF installed < ARRAY[0, 8, 0] THEN
                RAISE EXCEPTION
                    'pgvector 0.8.0 or newer is required, found %; upgrade it as its owner',
                    array_to_string(installed, '.');
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    # Extension downgrades are unsafe and unnecessary for the previous schema.
    pass
