"""Denormalized admin memory counts that never select memory content.

``memories`` keeps FORCE RLS, so an ``admin()`` session cannot group active
rows directly. Materialized counters on ``users`` and a content-free embedding
model registry keep administrative aggregates to a constant query budget while
preserving the hard isolation barrier.
"""

from __future__ import annotations

from alembic import op

revision = "0013_admin_memory_aggregates"
down_revision = "0012_memory_profile_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN active_memory_count BIGINT NOT NULL DEFAULT 0"
    )
    op.execute(
        """
        CREATE TABLE memory_embedding_models (
            embedding_model TEXT PRIMARY KEY,
            active_count BIGINT NOT NULL DEFAULT 0
                CHECK (active_count >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION recallum_adjust_active_memory_count()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.deleted_at IS NULL THEN
                    UPDATE users
                    SET active_memory_count = active_memory_count + 1
                    WHERE id = NEW.user_id;
                    IF NEW.embedding_model IS NOT NULL THEN
                        INSERT INTO memory_embedding_models (embedding_model, active_count)
                        VALUES (NEW.embedding_model, 1)
                        ON CONFLICT (embedding_model) DO UPDATE
                        SET active_count = memory_embedding_models.active_count + 1;
                    END IF;
                END IF;
                RETURN NEW;
            ELSIF TG_OP = 'DELETE' THEN
                IF OLD.deleted_at IS NULL THEN
                    UPDATE users
                    SET active_memory_count = GREATEST(active_memory_count - 1, 0)
                    WHERE id = OLD.user_id;
                    IF OLD.embedding_model IS NOT NULL THEN
                        UPDATE memory_embedding_models
                        SET active_count = GREATEST(active_count - 1, 0)
                        WHERE embedding_model = OLD.embedding_model;
                        DELETE FROM memory_embedding_models
                        WHERE embedding_model = OLD.embedding_model AND active_count = 0;
                    END IF;
                END IF;
                RETURN OLD;
            END IF;

            -- UPDATE: active <-> retired transitions and model restamps.
            IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
                UPDATE users
                SET active_memory_count = GREATEST(active_memory_count - 1, 0)
                WHERE id = NEW.user_id;
                IF OLD.embedding_model IS NOT NULL THEN
                    UPDATE memory_embedding_models
                    SET active_count = GREATEST(active_count - 1, 0)
                    WHERE embedding_model = OLD.embedding_model;
                    DELETE FROM memory_embedding_models
                    WHERE embedding_model = OLD.embedding_model AND active_count = 0;
                END IF;
            ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
                UPDATE users
                SET active_memory_count = active_memory_count + 1
                WHERE id = NEW.user_id;
                IF NEW.embedding_model IS NOT NULL THEN
                    INSERT INTO memory_embedding_models (embedding_model, active_count)
                    VALUES (NEW.embedding_model, 1)
                    ON CONFLICT (embedding_model) DO UPDATE
                    SET active_count = memory_embedding_models.active_count + 1;
                END IF;
            ELSIF NEW.deleted_at IS NULL
                AND OLD.embedding_model IS DISTINCT FROM NEW.embedding_model THEN
                IF OLD.embedding_model IS NOT NULL THEN
                    UPDATE memory_embedding_models
                    SET active_count = GREATEST(active_count - 1, 0)
                    WHERE embedding_model = OLD.embedding_model;
                    DELETE FROM memory_embedding_models
                    WHERE embedding_model = OLD.embedding_model AND active_count = 0;
                END IF;
                IF NEW.embedding_model IS NOT NULL THEN
                    INSERT INTO memory_embedding_models (embedding_model, active_count)
                    VALUES (NEW.embedding_model, 1)
                    ON CONFLICT (embedding_model) DO UPDATE
                    SET active_count = memory_embedding_models.active_count + 1;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER memories_active_count_aiud
        AFTER INSERT OR UPDATE OR DELETE ON memories
        FOR EACH ROW EXECUTE FUNCTION recallum_adjust_active_memory_count()
        """
    )

    # Owner can briefly lift FORCE RLS to backfill counters without selecting content
    # into the application layer.
    op.execute("ALTER TABLE memories NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE users AS u
        SET active_memory_count = COALESCE((
            SELECT COUNT(*)::bigint
            FROM memories AS m
            WHERE m.user_id = u.id AND m.deleted_at IS NULL
        ), 0)
        """
    )
    op.execute(
        """
        INSERT INTO memory_embedding_models (embedding_model, active_count)
        SELECT embedding_model, COUNT(*)::bigint
        FROM memories
        WHERE deleted_at IS NULL AND embedding_model IS NOT NULL
        GROUP BY embedding_model
        """
    )
    op.execute("ALTER TABLE memories FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS memories_active_count_aiud ON memories")
    op.execute("DROP FUNCTION IF EXISTS recallum_adjust_active_memory_count()")
    op.execute("DROP TABLE IF EXISTS memory_embedding_models")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS active_memory_count")
