"""Add monotonic generations for race-free materialized profile rebuilds."""

from __future__ import annotations

from alembic import op

revision = "0012_memory_profile_generation"
down_revision = "0011_memory_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN memory_generation BIGINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE memory_profiles ADD COLUMN generation BIGINT NOT NULL DEFAULT -1"
    )
    # Rows created by 0011 must be rebuilt against the first generation.
    op.execute("UPDATE memory_profiles SET generation = -1")


def downgrade() -> None:
    op.execute("ALTER TABLE memory_profiles DROP COLUMN IF EXISTS generation")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS memory_generation")
