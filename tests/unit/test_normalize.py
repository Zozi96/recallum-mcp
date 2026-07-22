"""Validation and normalization rules (task 3.2)."""

from __future__ import annotations

import pytest

from recallum.memory.normalize import (
    MemoryValidationError,
    content_hash,
    normalize_content,
    normalize_project,
    scope_for,
    validate_category,
    validate_importance,
    validate_metadata,
)


def test_normalize_content_trims_and_collapses_whitespace():
    assert normalize_content("  hello\n\n  world \t ", 100) == "hello world"


def test_normalize_content_rejects_empty():
    with pytest.raises(MemoryValidationError):
        normalize_content("   \n\t ", 100)


def test_normalize_content_enforces_max_chars():
    with pytest.raises(MemoryValidationError):
        normalize_content("x" * 11, 10)


def test_normalize_project_none_and_blank():
    assert normalize_project(None, 100) is None
    assert normalize_project("   ", 100) is None
    assert normalize_project("  mi-proyecto  ", 100) == "mi-proyecto"


def test_validate_category():
    assert validate_category("decision") == "decision"
    with pytest.raises(MemoryValidationError):
        validate_category("opinion")


def test_scope_for_project():
    assert scope_for(None) == "global"
    assert scope_for("recallum") == "project"


def test_validate_importance_bounds():
    assert validate_importance(0) == 0
    assert validate_importance(10) == 10
    with pytest.raises(MemoryValidationError):
        validate_importance(11)
    with pytest.raises(MemoryValidationError):
        validate_importance(True)


def test_validate_metadata_ok():
    assert validate_metadata({"k": "v", "n": 1, "f": True}, 1024, 10) == {
        "k": "v",
        "n": 1,
        "f": True,
    }
    assert validate_metadata(None, 1024, 10) == {}


def test_validate_metadata_rejects_nested_values():
    with pytest.raises(MemoryValidationError):
        validate_metadata({"k": {"nested": 1}}, 1024, 10)


def test_validate_metadata_rejects_too_many_keys():
    with pytest.raises(MemoryValidationError):
        validate_metadata({f"k{i}": i for i in range(5)}, 1024, 4)


def test_validate_metadata_rejects_oversized():
    with pytest.raises(MemoryValidationError):
        validate_metadata({"k": "x" * 100}, 50, 10)


def test_content_hash_stable_for_normalized_equivalents():
    assert content_hash("hello world") == content_hash("hello world")
    assert content_hash("hello world") != content_hash("hello worlds")
