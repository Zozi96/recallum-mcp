"""Invalidate materialized profiles after the static-eligibility policy change.

Data-only: every ``memory_profiles`` row is marked ``generation=-1`` so the
next read rebuilds under preference/constraint-only static. Source memories,
skills, counters, categories, and importance are untouched.

The owner migration briefly lifts FORCE RLS on ``memory_profiles`` only,
runs the UPDATE, and restores FORCE RLS before commit. The same
invalidation runs on downgrade; old static contents are not restored —
policy returns via rebuild. Alembic's transaction rolls the RLS flags
back with the UPDATE if anything fails.
"""

from __future__ import annotations

from alembic import op

revision = "0020_invalidate_memory_profiles"
down_revision = "0019_memory_code_anchors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _invalidate_profiles()


def downgrade() -> None:
    _invalidate_profiles()


def _invalidate_profiles() -> None:
    op.execute("ALTER TABLE memory_profiles NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE memory_profiles SET generation = -1")
    op.execute("ALTER TABLE memory_profiles FORCE ROW LEVEL SECURITY")
