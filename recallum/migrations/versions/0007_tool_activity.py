"""Add content-free operational telemetry for authenticated MCP tool calls."""

from __future__ import annotations

from alembic import op

revision = "0007_tool_activity"
down_revision = "0006_web_session_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deliberately no RLS: operators need cross-user aggregates, while
    # application self-service queries explicitly filter by user_id. This
    # boundary is safe only while the table contains operational metadata:
    # never add queries, memory content, result fragments, or similar text.
    op.execute(
        """
        CREATE TABLE tool_activity (
            id              UUID PRIMARY KEY,
            user_id         UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            tool_name       VARCHAR(64) NOT NULL,
            project         VARCHAR(200),
            duration_ms     INTEGER NOT NULL CHECK (duration_ms >= 0),
            result_count    INTEGER NOT NULL CHECK (result_count >= 0),
            degraded        BOOLEAN NOT NULL DEFAULT false,
            failed          BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_tool_activity_user_created_at "
        "ON tool_activity (user_id, created_at DESC)"
    )
    op.execute(
        "COMMENT ON TABLE tool_activity IS "
        "'Operational metadata only; intentionally outside RLS. "
        "Must never contain queries, memory content, or result fragments.'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE tool_activity")
