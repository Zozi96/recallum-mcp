"""Database model metadata checks."""

from pathlib import Path

from recallum.db.models import Memory

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "recallum"
    / "migrations"
    / "versions"
    / "0016_memory_structured_provenance.py"
)


def test_provenance_migration_upgrade_and_downgrade_sql():
    source = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0016_memory_provenance"' in source
    assert 'down_revision = "0015_memory_expiry"' in source
    assert "ADD COLUMN source_type TEXT NOT NULL DEFAULT 'unknown'" in source
    assert "ADD CONSTRAINT ck_memories_source_type" in source
    assert "ADD COLUMN source_ref TEXT" in source
    assert "DROP CONSTRAINT ck_memories_source_type" in source
    assert "DROP COLUMN source_ref" in source
    assert "DROP COLUMN source_type" in source


def test_source_type_check_constraint_is_present_without_derived_from():
    names = {constraint.name for constraint in Memory.__table__.constraints}
    assert "ck_memories_source_type" in names
    assert "derived_from" not in Memory.__table__.columns
    assert "source_type" in Memory.__table__.columns
    assert "source_ref" in Memory.__table__.columns


def test_active_created_index_metadata_is_partial():
    index = next(
        index
        for index in Memory.__table__.indexes
        if index.name == "ix_memories_user_active_created"
    )

    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"
