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
_KIND_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "recallum"
    / "migrations"
    / "versions"
    / "0017_coding_memory_kinds.py"
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


def test_kind_migration_upgrade_and_downgrade_sql():
    source = _KIND_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0017_coding_memory_kinds"' in source
    assert 'down_revision = "0016_memory_provenance"' in source
    assert "ADD COLUMN kind TEXT" in source
    assert "ADD CONSTRAINT ck_memories_kind" in source
    assert "DROP CONSTRAINT ck_memories_kind" in source
    assert "DROP COLUMN kind" in source


def test_kind_check_constraint_is_present_and_orthogonal_to_category():
    names = {constraint.name for constraint in Memory.__table__.constraints}
    assert "ck_memories_kind" in names
    assert "ck_memories_category" in names
    assert "kind" in Memory.__table__.columns
    assert Memory.__table__.columns["kind"].nullable is True
    # kind never widens category's own enum.
    category_check = next(
        c for c in Memory.__table__.constraints if c.name == "ck_memories_category"
    )
    assert "failure" not in str(category_check.sqltext)


def test_active_created_index_metadata_is_partial():
    index = next(
        index
        for index in Memory.__table__.indexes
        if index.name == "ix_memories_user_active_created"
    )

    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"
