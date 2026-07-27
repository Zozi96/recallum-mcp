"""Database model metadata checks."""

from recallum.db.models import Memory


def test_active_created_index_metadata_is_partial():
    index = next(
        index
        for index in Memory.__table__.indexes
        if index.name == "ix_memories_user_active_created"
    )

    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"
