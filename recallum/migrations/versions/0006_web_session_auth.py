"""Add browser credentials and independently revocable web sessions."""

from __future__ import annotations

from alembic import op

revision = "0006_web_session_auth"
down_revision = "0005_supersession"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    op.execute(
        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        """
        CREATE TABLE web_sessions (
            id                  UUID PRIMARY KEY,
            user_id             UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            token_hash          CHAR(64) NOT NULL UNIQUE,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            idle_expires_at     TIMESTAMPTZ NOT NULL,
            absolute_expires_at TIMESTAMPTZ NOT NULL,
            rotated_to_id       UUID REFERENCES web_sessions (id) ON DELETE SET NULL,
            revoked_at          TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX ix_web_sessions_user_id ON web_sessions (user_id)")
    op.execute(
        "CREATE INDEX ix_web_sessions_rotated_to_id ON web_sessions (rotated_to_id) "
        "WHERE rotated_to_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE web_sessions")
    op.execute("ALTER TABLE users DROP COLUMN is_admin")
    op.execute("ALTER TABLE users DROP COLUMN password_hash")
