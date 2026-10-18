"""Settings validation that does not fit a boundary/readiness test file."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from recallum.auth.middleware import IDENTITY_CACHE_TTL
from recallum.config import (
    EMBEDDING_DIMENSIONS,
    IDENTITY_CACHE_TTL_SECONDS,
    DatabaseSettings,
    Settings,
)
from recallum.container import create_container
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
        "server_settings": {
            "statement_timeout": "10000",
            "hnsw.iterative_scan": "strict_order",
            "hnsw.ef_search": "100",
        },
    }


def test_ollama_dimensions_must_equal_the_stored_vector_width() -> None:
    settings = Settings(ollama={"dimensions": EMBEDDING_DIMENSIONS})
    assert settings.ollama.dimensions == EMBEDDING_DIMENSIONS

    with pytest.raises(ValidationError, match="stored vector width"):
        Settings(ollama={"dimensions": EMBEDDING_DIMENSIONS + 1})


def test_ollama_read_budget_defaults_bounds_and_wiring() -> None:
    settings = Settings()
    assert settings.ollama.read_timeout_seconds == 3.0
    assert settings.ollama.read_negative_window_seconds == 5.0
    assert settings.ollama.read_cache_size == 256
    ollama = settings.for_container()["ollama"]
    assert ollama["read_timeout_seconds"] == 3.0
    assert ollama["read_negative_window_seconds"] == 5.0
    assert ollama["read_cache_size"] == 256

    for field, bad in (
        ("read_timeout_seconds", 0),
        ("read_timeout_seconds", 61),
        ("read_negative_window_seconds", 0),
        ("read_negative_window_seconds", 301),
        ("read_cache_size", 0),
        ("read_cache_size", 10_001),
    ):
        with pytest.raises(ValidationError):
            Settings(ollama={field: bad})

    container = create_container(
        Settings(
            ollama={
                "read_timeout_seconds": 1.5,
                "read_negative_window_seconds": 2.5,
                "read_cache_size": 8,
            }
        )
    )
    kwargs = container.embedding_client.kwargs
    assert kwargs["read_timeout_seconds"]() == 1.5
    assert kwargs["read_negative_window_seconds"]() == 2.5
    assert kwargs["read_cache_size"]() == 8
    assert kwargs["timeout_seconds"]() == 30.0


def test_identity_cache_default_is_max_revocation_delay() -> None:
    settings = Settings()
    assert settings.auth.identity_cache_seconds == IDENTITY_CACHE_TTL_SECONDS == 30.0
    assert timedelta(seconds=30) == IDENTITY_CACHE_TTL
    assert Settings(auth={"identity_cache_seconds": 0}).auth.identity_cache_seconds == 0.0
    assert Settings(auth={"identity_cache_seconds": 5}).auth.identity_cache_seconds == 5.0

    assert create_container(settings).authenticator.kwargs["cache_ttl"]().total_seconds() == 30.0
    zero = create_container(Settings(auth={"identity_cache_seconds": 0}))
    five = create_container(Settings(auth={"identity_cache_seconds": 5}))
    assert zero.authenticator.kwargs["cache_ttl"]().total_seconds() == 0.0
    assert five.authenticator.kwargs["cache_ttl"]().total_seconds() == 5.0
