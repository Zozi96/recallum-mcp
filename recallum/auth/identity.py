"""Request-scoped identity derived from the authenticated API key.

The FastMCP auth middleware sets ``current_identity`` for the duration of a
tool call; tools read it via ``require_identity`` and never accept a user id
as an argument.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Identity:
    """The authenticated principal for one request."""

    user_id: uuid.UUID
    email: str
    api_key_id: uuid.UUID


current_identity: ContextVar[Identity | None] = ContextVar("recallum_identity", default=None)


@contextmanager
def identity_scope(identity: Identity) -> Iterator[Identity]:
    """Bind ``identity`` for the duration of the wrapped call."""
    token = current_identity.set(identity)
    try:
        yield identity
    finally:
        current_identity.reset(token)


def require_identity() -> Identity:
    """Return the current identity or fail closed when absent."""
    identity = current_identity.get()
    if identity is None:
        raise LookupError("no authenticated identity in scope")
    return identity
