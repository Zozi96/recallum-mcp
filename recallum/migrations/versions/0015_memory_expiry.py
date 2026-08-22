"""Optional declared expiry for short-lived "working memory".

Short-lived facts ("branch X is blocked this week") today pollute the
durable corpus until a manual stale-review notices them. ``expires_at`` lets
``remember``/``update`` declare a TTL; once past, the row is excluded from
every active-selection predicate (recall, context, list, get, similar,
related/graph, dedup-by-hash) without a background purge job -- a lazy
read-time filter only, the same shape as the existing ``deleted_at`` check
but orthogonal to it. Rows are retained, never physically deleted.

Dedup nuance: the active-by-hash lookup used by ``remember`` to detect exact
repeats now also excludes expired rows, so re-remembering the same content
after it expired creates a fresh row (with a fresh id and a fresh clock)
instead of silently reviving the stale one.

Additive and nullable with no default: existing rows get NULL (no expiry),
so today's durable-by-default behaviour is unaffected.
"""

from __future__ import annotations

from alembic import op

revision = "0015_memory_expiry"
down_revision = "0014_reconfirm_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE memories ADD COLUMN expires_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE memories DROP COLUMN expires_at")
