"""Declarative metadata root. Alembic migrations target ``Base.metadata``.

The application never calls ``create_all()``: the schema is owned by Alembic.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all Recallum models."""
