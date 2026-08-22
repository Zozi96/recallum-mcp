"""Unit tests for the non-English-content advisory heuristic."""

from __future__ import annotations

import pytest

from recallum.memory.language import looks_non_english


@pytest.mark.parametrize(
    "content",
    [
        "El equipo decidió usar FastAPI en vez de Flask para el backend.",
        "No usamos Docker en producción, preferimos Kubernetes directo.",
        "La configuración de recallum/memory/service.py está en inglés.",
    ],
)
def test_flags_spanish_prose(content: str) -> None:
    assert looks_non_english(content) is True


@pytest.mark.parametrize(
    "content",
    [
        "We use FastAPI for the backend and Postgres for storage.",
        "The team decided to migrate the auth_service module to FastAPI.",
        "This is a short English sentence about nothing in particular.",
    ],
)
def test_does_not_flag_english_prose(content: str) -> None:
    assert looks_non_english(content) is False


@pytest.mark.parametrize(
    "content",
    [
        "",
        "prefiero tabs",
        "misma nota",
        "usamos FastAPI",
        "Run docker-compose up --build then check logs/app.log for errors.",
        "git commit -m 'fix: update user_service.py path handling' --no-verify",
        "Prefer async functions in api/routes/users.py for I/O bound handlers.",
    ],
)
def test_does_not_flag_short_or_identifier_heavy_content(content: str) -> None:
    assert looks_non_english(content) is False
