"""Materialized always-on memory profiles per user (and optional project).

Profiles are projections of active memories, not a second knowledge base.
The empty-string project key is the user-global profile; a non-empty project
is a project-scoped key. RLS isolation matches ``memories``: forced policies
keyed on ``app.current_user_id``.
"""

from __future__ import annotations

from alembic import op

revision = "0011_memory_profiles"
down_revision = "0010_trigram_leg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_profiles (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project TEXT NOT NULL DEFAULT '',
            static_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            dynamic_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_memory_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
            content_hash CHAR(64) NOT NULL,
            built_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, project)
        )
        """
    )
    op.execute("ALTER TABLE memory_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE memory_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY memory_profiles_user_isolation ON memory_profiles
            FOR ALL
            USING (user_id::text = current_setting('app.current_user_id', true))
            WITH CHECK (user_id::text = current_setting('app.current_user_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_profiles")
