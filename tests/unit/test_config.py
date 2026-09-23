"""Settings validation that does not fit a boundary/readiness test file."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from recallum.config import EMBEDDING_DIMENSIONS, DatabaseSettings, Settings
from tests.fakes import build_test_container


def test_database_timeouts_have_engine_defaults_and_bounds() -> None:
    settings = DatabaseSettings()
    assert settings.pool_timeout_seconds == 30.0
    assert settings.connect_timeout_seconds == 5.0
    assert settings.command_timeout_seconds == 30.0
    assert settings.statement_timeout_seconds == 30.0

    for field in (
        "pool_timeout_seconds",
        "connect_timeout_seconds",
        "command_timeout_seconds",
        "statement_timeout_seconds",
    ):
        with pytest.raises(ValidationError):
            DatabaseSettings(**{field: 0})
        with pytest.raises(ValidationError):
            DatabaseSettings(**{field: 601})


def test_engine_deadlines_come_from_database_not_readiness() -> None:
    """The engine must use ``database.*`` timeouts, not the probe's budget."""
    container, _ = build_test_container(
        settings=Settings(
            database={
                "pool_timeout_seconds": 7.0,
                "connect_timeout_seconds": 8.0,
                "command_timeout_seconds": 9.0,
                "statement_timeout_seconds": 10.0,
            },
            readiness={
                "per_dependency_timeout_seconds": 2.0,
                "database_pool_timeout_seconds": 1.5,
                "database_connect_timeout_seconds": 1.5,
                "database_command_timeout_seconds": 1.5,
                "database_statement_timeout_seconds": 1.5,
            },
        )
    )

    engine_kwargs = container.engine.kwargs
    assert engine_kwargs["pool_timeout"]() == 7.0
    assert engine_kwargs["connect_args"]() == {
        "timeout": 8.0,
        "command_timeout": 9.0,
        "server_settings": {"statement_timeout": "10000"},
    }


def test_ollama_dimensions_must_equal_the_stored_vector_width() -> None:
    settings = Settings(ollama={"dimensions": EMBEDDING_DIMENSIONS})
    assert settings.ollama.dimensions == EMBEDDING_DIMENSIONS

    with pytest.raises(ValidationError, match="stored vector width"):
        Settings(ollama={"dimensions": EMBEDDING_DIMENSIONS + 1})
